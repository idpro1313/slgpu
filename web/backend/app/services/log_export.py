# GRACE[M-LOG-EXPORT][pipeline][BLOCK_LOG_EXPORT]
"""Полная выгрузка строк из Loki в файл ``ndjson.gz`` (постраничный query_range).

CONTRACT:
  PURPOSE: Исчерпать все строки за [time_from, time_to] для заданного LogQL без лимита числа строк.
  INPUTS: export row id, job id; merged stack.
  OUTPUTS: артефакт под ``${WEB_DATA_DIR}/.slgpu/log-exports/``, обновление ``log_exports``.
"""
from __future__ import annotations

import gzip
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from app.db.session import session_scope
from app.models.job import Job, JobStatus
from app.models.log_export import LogExport, LogExportStatus
from app.services.log_report import (
    _ts_ns,
    parse_loki_streams,
    redact_line_full,
    resolved_logql,
    validate_period,
)
from app.services.loki_client import query_range as loki_query_range
from app.services.stack_config import sync_merged_flat

logger = logging.getLogger(__name__)

# Согласовано с ``limits_config.retention_period`` / ``max_query_lookback`` в
# loki-config.yaml.tmpl (в шаблоне slgpu — 2880h ≈ 120 суток).
EXPORT_MAX_PERIOD_HOURS = 2880
_PAGE_LIMIT = 25_000

_RETENTION_NOTE = (
    "Loki хранит строки не дольше retention (см. limits_config.retention_period в конфиге "
    "мониторинга); за пределами этого окна данные отсутствуют."
)


class ExportCancelled(Exception):
    """Пользователь или runner отменил job."""


@dataclass
class _ExportState:
    lines_written: int = 0
    last_progress_flush: int = 0


def _esc_logql_label_value(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def _inject_logql_selectors(base: str, extras: list[str]) -> str:
    """Добавить пары ``key="value"`` внутрь первого селектора ``{...}``."""

    s = base.strip()
    if not s.startswith("{") or "}" not in s:
        return s
    depth = 0
    end_idx = -1
    for i, ch in enumerate(s):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break
    if end_idx < 0:
        return s
    inner = s[1:end_idx].strip()
    rest = s[end_idx + 1 :]
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    for e in extras:
        if e not in parts:
            parts.append(e)
    return "{" + ",".join(parts) + "}" + rest


def build_export_logql(
    *,
    scope: str,
    logql_custom: str | None,
    container: str | None,
    compose_service: str | None,
    compose_project: str | None,
    slgpu_slot: str | None,
    slgpu_engine: str | None,
    slgpu_preset: str | None,
    slgpu_run_id: str | None,
) -> str:
    if scope == "custom":
        if not logql_custom or not logql_custom.strip():
            raise ValueError("logql обязателен при scope=custom")
        base = logql_custom.strip()
    else:
        base = resolved_logql(scope, None)

    extras: list[str] = []
    if container:
        extras.append(f'container="{_esc_logql_label_value(container)}"')
    if compose_service:
        extras.append(f'compose_service="{_esc_logql_label_value(compose_service)}"')
    if compose_project:
        extras.append(f'compose_project="{_esc_logql_label_value(compose_project)}"')
    if slgpu_slot:
        extras.append(f'slgpu_slot="{_esc_logql_label_value(slgpu_slot)}"')
    if slgpu_engine:
        extras.append(f'slgpu_engine="{_esc_logql_label_value(slgpu_engine)}"')
    if slgpu_preset:
        extras.append(f'slgpu_preset="{_esc_logql_label_value(slgpu_preset)}"')
    if slgpu_run_id:
        extras.append(f'slgpu_run_id="{_esc_logql_label_value(slgpu_run_id)}"')

    if not extras:
        if scope == "custom":
            q = base
            if "\n" in q or "\r" in q:
                raise ValueError("logql не должен содержать переводов строк")
            if not q.startswith("{"):
                raise ValueError("logql должен начинаться с селектора labels «{»")
            return q[:4096]
        return base

    merged_sel = _inject_logql_selectors(base, extras)
    if "\n" in merged_sel or "\r" in merged_sel:
        raise ValueError("logql не должен содержать переводов строк")
    if not merged_sel.startswith("{"):
        raise ValueError("logql должен начинаться с селектора labels «{»")
    return merged_sel[:4096]


async def _job_cancelled(job_id: int) -> bool:
    async with session_scope() as session:
        j = await session.get(Job, job_id)
        return j is None or j.status == JobStatus.CANCELLED


async def _flush_progress(job_id: int, state: _ExportState) -> None:
    if state.lines_written - state.last_progress_flush < 5000:
        return
    state.last_progress_flush = state.lines_written
    async with session_scope() as session:
        j = await session.get(Job, job_id)
        if j and j.status == JobStatus.RUNNING:
            j.message = f"log export: {state.lines_written} строк"


def _write_sorted_tuples(
    gz: IO[str],
    tuples: list[tuple[int, dict[str, str], str]],
    *,
    state: _ExportState,
    redact: bool,
) -> None:
    tuples.sort(key=lambda x: (x[0], json.dumps(x[1], sort_keys=True, ensure_ascii=False), x[2]))
    for ts_ns, labels, raw in tuples:
        line_out = redact_line_full(raw) if redact else raw
        rec = {"ts_ns": ts_ns, "labels": labels, "line": line_out}
        gz.write(json.dumps(rec, ensure_ascii=False) + "\n")
        state.lines_written += 1


async def _export_partition(
    merged: dict[str, str],
    logql: str,
    lo_ns: int,
    hi_ns: int,
    job_id: int,
    gz: IO[str],
    state: _ExportState,
    *,
    redact: bool,
) -> None:
    """Рекурсивное деление окна по времени, пока страница Loki не перестанет насыщаться."""

    if lo_ns > hi_ns:
        return
    if await _job_cancelled(job_id):
        raise ExportCancelled()

    payload = await loki_query_range(
        query=logql,
        start_ns=lo_ns,
        end_ns=hi_ns,
        limit=_PAGE_LIMIT,
        merged=merged,
        timeout_sec=240.0,
        direction="forward",
    )
    tuples = parse_loki_streams(payload)
    await _flush_progress(job_id, state)

    if not tuples:
        return
    if len(tuples) < _PAGE_LIMIT:
        _write_sorted_tuples(gz, tuples, state=state, redact=redact)
        await _flush_progress(job_id, state)
        return
    if lo_ns == hi_ns:
        logger.warning(
            "[log_export][partition][BLOCK_TRUNC_SAME_NS] job_id=%s ts=%s lines=%s",
            job_id,
            lo_ns,
            len(tuples),
        )
        _write_sorted_tuples(gz, tuples, state=state, redact=redact)
        await _flush_progress(job_id, state)
        return

    mid = (lo_ns + hi_ns) // 2
    await _export_partition(merged, logql, lo_ns, mid, job_id, gz, state, redact=redact)
    await _export_partition(merged, logql, mid + 1, hi_ns, job_id, gz, state, redact=redact)


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


def _export_paths(merged: dict[str, str], export_id: int, tag: str) -> tuple[Path, Path]:
    root = Path(str(merged.get("WEB_DATA_DIR") or "")).resolve()
    sub = root / ".slgpu" / "log-exports"
    fname = f"export-{export_id}-{tag}.ndjson.gz"
    return sub, sub / fname


async def run_log_export_pipeline(job_id: int, export_id: int) -> None:
    merged = sync_merged_flat()
    state = _ExportState()

    async with session_scope() as sess:
        row = await sess.get(LogExport, export_id)
        if row is None:
            logger.error("[log_export][pipeline][BLOCK_NO_ROW] export_id=%s", export_id)
            await _finalize_job(job_id, exit_code=1, message="log export row missing")
            return
        row.status = LogExportStatus.RUNNING

    try:
        async with session_scope() as sess:
            ex = await sess.get(LogExport, export_id)
            if ex is None:
                raise RuntimeError("export disappeared")
            dt_from_a, dt_to_a = validate_period(
                ex.time_from, ex.time_to, max_hours=EXPORT_MAX_PERIOD_HOURS
            )
            logql_str = (ex.logql or "").strip()
            redact = bool(ex.redact_secrets)

        start_ns = _ts_ns(dt_from_a)
        end_ns = _ts_ns(dt_to_a)

        tag = uuid.uuid4().hex[:10]
        out_dir, final_path = _export_paths(merged, export_id, tag)
        out_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = final_path.with_suffix(final_path.suffix + ".part")

        try:
            with gzip.open(tmp_path, "wt", encoding="utf-8", newline="\n") as gz:
                await _export_partition(
                    merged,
                    logql_str,
                    start_ns,
                    end_ns,
                    job_id,
                    gz,
                    state,
                    redact=redact,
                )
            tmp_path.replace(final_path)
        except BaseException:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        rel = Path(".slgpu") / "log-exports" / final_path.name
        byte_size = final_path.stat().st_size

        async with session_scope() as sess:
            ex2 = await sess.get(LogExport, export_id)
            if ex2 is not None:
                ex2.status = LogExportStatus.SUCCEEDED
                ex2.artifact_relpath = str(rel).replace("\\", "/")
                ex2.line_count = state.lines_written
                ex2.byte_size = int(byte_size)
                ex2.retention_note = _RETENTION_NOTE
                ex2.error_message = None

        await _finalize_job(
            job_id,
            exit_code=0,
            message=f"log export done: {state.lines_written} строк",
        )
        logger.info(
            "[log_export][pipeline][BLOCK_DONE] export_id=%s lines=%s bytes=%s",
            export_id,
            state.lines_written,
            byte_size,
        )
    except ExportCancelled:
        logger.info("[log_export][pipeline][BLOCK_CANCELLED] export_id=%s", export_id)
        async with session_scope() as sess:
            ex3 = await sess.get(LogExport, export_id)
            if ex3 is not None:
                ex3.status = LogExportStatus.FAILED
                ex3.error_message = "экспорт отменён (job cancelled)"
        await _finalize_job(job_id, exit_code=1, message="cancelled")
    except Exception as exc:
        logger.exception("[log_export][pipeline][BLOCK_FAIL]")
        errmsg = str(exc)[:8000]
        async with session_scope() as sess:
            ex4 = await sess.get(LogExport, export_id)
            if ex4 is not None:
                ex4.status = LogExportStatus.FAILED
                ex4.error_message = errmsg
        await _finalize_job(job_id, exit_code=1, message=errmsg[:2000])

