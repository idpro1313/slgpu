# GRACE[M-LOG-REPORT][aggregate][BLOCK_LOG_REPORT_AGG]
"""Сбор фактов из Loki и генерация Markdown через LiteLLM.

CONTRACT:
  PURPOSE: Построить детерминированный JSON фактов и LLM/fallback-сводку для LogReport.
  INPUTS: report row id, job id; ключи LiteLLM из настроек.
  OUTPUTS: обновление LogReport и Job статусов.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models.job import Job, JobStatus
from app.models.log_report import LogReport, LogReportStatus
from app.services import app_settings
from app.services.litellm import litellm_http_base_sync
from app.services.loki_client import query_range as loki_query_range
from app.services.stack_config import sync_merged_flat

logger = logging.getLogger(__name__)

_LOGQL_SLGPU = '{job="docker-logs", container=~"slgpu-.*|slgpu-monitoring-.*|slgpu-proxy-.*"}'
_LOGQL_ALL = '{job="docker-logs"}'

_MAX_PERIOD_HOURS = 168
_SAMPLE_PER_CAT = 20
_MAX_SAMPLE_CHARS = 4000

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)(hf_token|authorization|bearer)(\s*[=:\"\'\s]+)([^\s\"\'\)]+)",
        ),
        r"\1\2***",
    ),
    (re.compile(r"(?i)(sk-[a-zA-Z0-9_-]{10,})"), "***"),
    (re.compile(r"(?i)(password\s*[=:]\s*)(\S+)"), r"\1***"),
    (re.compile(r"(?i)(LITELLM_MASTER_KEY\s*[=:]\s*)(\S+)"), r"\1***"),
]

_ERROR_RE = re.compile(
    r"(?i)(\blevel=\"?error\"?\b|\berror(s|ed)?\b|\bexception\b|\btraceback\b|\bfatal\b|\bpanic\b|\bfailed\b)"
)
_WARN_RE = re.compile(r"(?i)(\blevel=\"?warn(ing)?\"?\b|\bwarn(ing)?\b)")
_OOM_RE = re.compile(r"(?i)(\boom\b|\bout of memory\b|\bcuda out of memory\b)")
_CUDA_NEEDLES = ("cuda error", "cudaGetDevice", "nvidia")

_BLOCK_MARKER_RE = re.compile(r"\[(BLOCK_[A-Z0-9_]+)\]")


def resolved_logql(scope: str, custom: str | None) -> str:
    if scope == "custom":
        if not custom or not custom.strip():
            raise ValueError("logql обязателен при scope=custom")
        q = custom.strip()
        if "\n" in q or "\r" in q:
            raise ValueError("logql не должен содержать переводов строк")
        if not q.startswith("{"):
            raise ValueError("logql должен начинаться с селектора labels «{»")
        return q[:4096]
    if scope == "all":
        return _LOGQL_ALL
    return _LOGQL_SLGPU


def validate_period(dt_from: datetime, dt_to: datetime) -> tuple[datetime, datetime]:
    if dt_to <= dt_from:
        raise ValueError("time_to должно быть больше time_from")
    a = dt_from if dt_from.tzinfo else dt_from.replace(tzinfo=timezone.utc)
    b = dt_to if dt_to.tzinfo else dt_to.replace(tzinfo=timezone.utc)
    delta_h = (b - a).total_seconds() / 3600
    if delta_h > _MAX_PERIOD_HOURS:
        raise ValueError(
            f"интервал не более {_MAX_PERIOD_HOURS} ч (согласовано с max_query_lookback Loki)"
        )
    return a, b


def _ts_ns(dt: datetime) -> int:
    """Наносекунды UNIX UTC без float drift (важно для Loki query_range)."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    td = dt - epoch
    return td.days * 86_400 * 1_000_000_000 + td.seconds * 1_000_000_000 + td.microseconds * 1_000


def redact_line(line: str) -> str:
    s = line
    for rx, repl in _REDACT_PATTERNS:
        s = rx.sub(repl, s)
    return s[:_MAX_SAMPLE_CHARS]


def parse_loki_streams(data: dict[str, Any]) -> list[tuple[int, dict[str, str], str]]:
    """Список (timestamp_ns, stream_labels, line)."""

    out: list[tuple[int, dict[str, str], str]] = []
    res = data.get("data") or {}
    result_type = res.get("resultType")
    if result_type != "streams":
        return out
    for stream in res.get("result") or []:
        labels = stream.get("stream") or {}
        if not isinstance(labels, dict):
            labels = {}
        str_labels = {str(k): str(v) for k, v in labels.items()}
        for ts, raw in stream.get("values") or []:
            try:
                t_ns = int(ts)
            except (TypeError, ValueError):
                continue
            line = raw if isinstance(raw, str) else str(raw)
            out.append((t_ns, str_labels, line))
    return out


def _has_errorish(line: str) -> bool:
    return bool(_ERROR_RE.search(line))


def _has_warningish(line: str) -> bool:
    return bool(_WARN_RE.search(line))


def _has_oom(line: str) -> bool:
    return bool(_OOM_RE.search(line))


def _bucket_5m(ts_ns: int) -> int:
    return ts_ns // (5 * 60 * 1_000_000_000)


def build_facts_bundle(
    lines: list[tuple[int, dict[str, str], str]],
    *,
    time_from: datetime,
    time_to: datetime,
    logql: str,
    max_lines: int,
    loki_truncated_hint: bool,
) -> dict[str, Any]:
    by_container_counts: defaultdict[str, int] = defaultdict(int)
    severity_hits = {
        "errorish": defaultdict(int),
        "warningish": defaultdict(int),
        "oom": defaultdict(int),
        "cuda": defaultdict(int),
        "block_markers": defaultdict(int),
    }
    samples = {
        "errorish": list[str](),
        "warningish": list[str](),
        "oom": list[str](),
        "cuda": list[str](),
        "block_markers": list[str](),
    }
    timeline: defaultdict[int, int] = defaultdict(int)

    for ts_ns, labels, raw in lines:
        line_l = raw.lower()
        cname = (labels.get("container") or "(unknown)")[:128]
        by_container_counts[cname] += 1
        timeline[_bucket_5m(ts_ns)] += 1

        for bm in _BLOCK_MARKER_RE.finditer(raw):
            name = bm.group(1)
            severity_hits["block_markers"][name] += 1
            if len(samples["block_markers"]) < _SAMPLE_PER_CAT:
                samples["block_markers"].append(redact_line(raw))

        oom_hit = False
        if _has_oom(raw):
            severity_hits["oom"][cname] += 1
            if len(samples["oom"]) < _SAMPLE_PER_CAT:
                samples["oom"].append(redact_line(raw))
            oom_hit = True

        cuda_hit = False
        if not oom_hit:
            for n in _CUDA_NEEDLES:
                if n in line_l:
                    severity_hits["cuda"][cname] += 1
                    if len(samples["cuda"]) < _SAMPLE_PER_CAT:
                        samples["cuda"].append(redact_line(raw))
                    cuda_hit = True
                    break

        err_hit = _has_errorish(raw)
        if err_hit and not cuda_hit:
            severity_hits["errorish"][cname] += 1
            if len(samples["errorish"]) < _SAMPLE_PER_CAT:
                samples["errorish"].append(redact_line(raw))

        warn_hit = _has_warningish(raw)
        if warn_hit and not err_hit:
            severity_hits["warningish"][cname] += 1
            if len(samples["warningish"]) < _SAMPLE_PER_CAT:
                samples["warningish"].append(redact_line(raw))

    top_containers = sorted(
        by_container_counts.items(),
        key=lambda x: (-x[1], x[0]),
    )[:40]

    def _hit_dict(d: defaultdict[str, int]) -> dict[str, int]:
        return dict(sorted(d.items(), key=lambda x: (-x[1], x[0]))[:30])

    block_top = severity_hits["block_markers"]

    bucket_list = sorted(timeline.keys())
    timeline_out = []
    for b in bucket_list[:500]:
        timeline_out.append(
            {
                "bucket_index": b,
                "count": timeline[b],
            }
        )

    return {
        "meta": {
            "time_from": time_from.isoformat(),
            "time_to": time_to.isoformat(),
            "logql": logql,
            "lines_used": len(lines),
            "max_lines_requested": max_lines,
            "loki_response_truncated": loki_truncated_hint,
        },
        "by_container_total": dict(top_containers),
        "severity_by_container": {
            "errorish": _hit_dict(severity_hits["errorish"]),
            "warningish": _hit_dict(severity_hits["warningish"]),
            "oom": _hit_dict(severity_hits["oom"]),
            "cuda": _hit_dict(severity_hits["cuda"]),
        },
        "block_marker_counts": _hit_dict(block_top),
        "samples_redacted": samples,
        "timeline_buckets_5m": timeline_out,
    }


def facts_json_for_prompt(facts: dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False, indent=2)


def _top_items(d: dict[str, Any], *, limit: int = 8) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    for key, value in d.items():
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        items.append((str(key), count))
    return sorted(items, key=lambda x: (-x[1], x[0]))[:limit]


def render_fallback_markdown(facts: dict[str, Any], *, reason: str | None = None) -> str:
    """Локальная Markdown-сводка, когда LiteLLM недоступен или вернул 5xx."""

    meta = facts.get("meta") if isinstance(facts.get("meta"), dict) else {}
    containers = facts.get("by_container_total")
    if not isinstance(containers, dict):
        containers = {}
    severity = facts.get("severity_by_container")
    if not isinstance(severity, dict):
        severity = {}
    block_markers = facts.get("block_marker_counts")
    if not isinstance(block_markers, dict):
        block_markers = {}

    lines_used = meta.get("lines_used", 0)
    max_requested = meta.get("max_lines_requested", 0)
    truncated = "да" if meta.get("loki_response_truncated") else "нет"

    out = [
        "# Отчёт по логам",
        "",
        "> LiteLLM-сводка недоступна; показан локальный отчёт по детерминированным фактам.",
    ]
    if reason:
        out.extend(["", f"Причина: `{reason[:500]}`"])

    out.extend(
        [
            "",
            "## Краткое резюме",
            f"- Интервал: `{meta.get('time_from', '?')}` → `{meta.get('time_to', '?')}`.",
            f"- Использовано строк: `{lines_used}` из лимита `{max_requested}`; усечение Loki: `{truncated}`.",
            f"- LogQL: `{meta.get('logql', '?')}`.",
        ]
    )

    out.extend(["", "## Контейнеры с наибольшим числом строк"])
    top_containers = _top_items(containers)
    if top_containers:
        out.extend([f"- `{name}`: {count}" for name, count in top_containers])
    else:
        out.append("- Нет данных по контейнерам.")

    out.extend(["", "## Что требует внимания"])
    attention: list[str] = []
    for bucket_name, title in (
        ("oom", "OOM"),
        ("cuda", "CUDA/NVIDIA"),
        ("errorish", "ошибки/исключения"),
        ("warningish", "предупреждения"),
    ):
        bucket = severity.get(bucket_name)
        if not isinstance(bucket, dict):
            continue
        for container, count in _top_items(bucket, limit=5):
            attention.append(f"- `{container}`: {title} — {count}")
    if attention:
        out.extend(attention)
    else:
        out.append("- Явных error/warning/OOM/CUDA-срабатываний в выбранной выборке не найдено.")

    out.extend(["", "## GRACE/BLOCK-маркеры"])
    top_blocks = _top_items(block_markers)
    if top_blocks:
        out.extend([f"- `{name}`: {count}" for name, count in top_blocks])
    else:
        out.append("- BLOCK-маркеры в выборке не найдены.")

    out.extend(
        [
            "",
            "## Рекомендованные шаги",
            "- Откройте JSON фактов ниже и проверьте примеры строк в `samples_redacted`.",
            "- Если нужен LLM-анализ, проверьте LiteLLM Proxy, выбранную модель и маршрут `/v1/chat/completions`.",
            "- При большом числе CUDA/OOM-событий сопоставьте контейнеры со слотами инференса и их GPU-масками.",
        ]
    )
    return "\n".join(out)


def _system_prompt_ru() -> str:
    return (
        "Ты аналитик эксплуатации LLM-стенда slgpu (Docker + vLLM/SGLang + мониторинг). "
        "По приложенному JSON с агрегированными фактами из Loki напиши краткий отчёт на русском "
        "(Markdown): (1) краткое резюме, (2) что пошло не так / риски, (3) рекомендованные шаги, "
        "(4) список контейнеров, требующих внимания. Не выдумывай строки логов; опирайся только на поля JSON. "
        "Если данных мало — так и напиши."
    )


async def call_litellm_chat(
    *,
    session: AsyncSession,
    llm_model: str,
    user_content: str,
    timeout_sec: float = 120.0,
) -> str:
    key = await app_settings.get_litellm_api_key(session)
    if not key:
        raise RuntimeError("не задан LITELLM_API_KEY в настройках «8. Секреты приложения»")

    base = litellm_http_base_sync()
    url = f"{base}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    body = {
        "model": llm_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _system_prompt_ru()},
            {"role": "user", "content": user_content[:120_000]},
        ],
    }
    async with httpx.AsyncClient(timeout=timeout_sec, headers=headers) as client:
        r = await client.post(url, json=body)
        if r.status_code != 200:
            logger.warning(
                "[log_report][litellm][BLOCK_LLM_HTTP] status=%s body=%s",
                r.status_code,
                (r.text or "")[:800],
            )
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("пустой ответ LiteLLM: нет choices")
    msg = (choices[0] or {}).get("message") or {}
    content = msg.get("content")
    if not content or not str(content).strip():
        raise RuntimeError("пустое content от LiteLLM")
    return str(content).strip()


async def _finalize_job(
    job_id: int,
    *,
    exit_code: int,
    message: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    async with session_scope() as sess:
        j = await sess.get(Job, job_id)
        if j is None or j.status == JobStatus.CANCELLED:
            return
        j.exit_code = exit_code
        j.finished_at = now
        j.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        if message:
            j.message = message[:2000]


async def run_log_report_pipeline(job_id: int, report_id: int) -> None:
    """Вызывается из jobs runner (после перевода Job в RUNNING)."""

    merged = sync_merged_flat()

    async with session_scope() as sess:
        report = await sess.get(LogReport, report_id)
        if report is None:
            logger.error(
                "[log_report][pipeline][BLOCK_NO_REPORT] report_id=%s", report_id
            )
            await _finalize_job(job_id, exit_code=1, message="log report row missing")
            return
        report.status = LogReportStatus.RUNNING

    try:
        async with session_scope() as sess:
            report_row = await sess.get(LogReport, report_id)
            if report_row is None:
                raise RuntimeError("report disappeared")
            logql_str = (report_row.logql or "").strip()
            if not logql_str:
                logql_str = resolved_logql(report_row.scope, None)
            dt_from = report_row.time_from
            dt_to = report_row.time_to
            llm_model = report_row.llm_model
            max_lines = int(report_row.max_lines)

        dt_from_a, dt_to_a = validate_period(dt_from, dt_to)
        start_ns = _ts_ns(dt_from_a)
        end_ns = _ts_ns(dt_to_a)

        loki_payload = await loki_query_range(
            query=logql_str,
            start_ns=start_ns,
            end_ns=end_ns,
            limit=max_lines,
            merged=merged,
        )
        tuples = parse_loki_streams(loki_payload)
        loki_truncated = len(tuples) >= max_lines - 1
        tuples.sort(key=lambda x: x[0], reverse=True)
        clipped = tuples[:max_lines]

        facts = build_facts_bundle(
            clipped,
            time_from=dt_from_a,
            time_to=dt_to_a,
            logql=logql_str,
            max_lines=max_lines,
            loki_truncated_hint=loki_truncated,
        )
        user_blob = facts_json_for_prompt(facts)

        llm_warning: str | None = None
        try:
            async with session_scope() as sess:
                markdown = await call_litellm_chat(
                    session=sess,
                    llm_model=llm_model,
                    user_content=user_blob,
                )
        except Exception as exc:
            llm_warning = str(exc)[:8000]
            logger.warning(
                "[log_report][pipeline][BLOCK_LLM_FALLBACK] report_id=%s error=%s",
                report_id,
                llm_warning[:800],
            )
            markdown = render_fallback_markdown(facts, reason=llm_warning)

        async with session_scope() as sess:
            r2 = await sess.get(LogReport, report_id)
            if r2 is None:
                raise RuntimeError("report disappeared")
            r2.facts = facts
            r2.llm_markdown = markdown
            r2.status = LogReportStatus.SUCCEEDED
            r2.error_message = (
                f"LiteLLM недоступен, показана локальная сводка: {llm_warning}"
                if llm_warning
                else None
            )

        await _finalize_job(
            job_id,
            exit_code=0,
            message=(
                "log report succeeded with local fallback"
                if llm_warning
                else "log report succeeded"
            ),
        )
        logger.info(
            "[log_report][pipeline][BLOCK_DONE] report_id=%s lines=%s",
            report_id,
            len(clipped),
        )
    except Exception as exc:
        logger.exception("[log_report][pipeline][BLOCK_FAIL]")
        errmsg = str(exc)[:8000]
        async with session_scope() as sess:
            r3 = await sess.get(LogReport, report_id)
            if r3 is not None:
                r3.status = LogReportStatus.FAILED
                r3.error_message = errmsg
        await _finalize_job(job_id, exit_code=1, message=errmsg[:2000])
