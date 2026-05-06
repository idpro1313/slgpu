"""Stack configuration in SQLite (web no longer reads main.env at runtime).

``stack_params`` table: one row per key (``param_key``, ``param_value``, ``is_secret``).

Legacy ``settings`` rows ``cfg.stack`` / ``cfg.secrets`` (JSON blobs) are migrated once
to ``stack_params``; afterwards those settings keys are kept as ``{}`` for compatibility.
``cfg.meta`` — ``{installed, installed_at, source}`` (unchanged).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select

from app.services.env_key_aliases import apply_vllm_aliases_to_merged
from app.services.stack_errors import MissingStackParams
from app.services.stack_registry import (
    CANONICAL_STACK_KEYS,
    STACK_KEY_REGISTRY,
    is_secret_key,
    missing_keys_in_db,
)

logger = logging.getLogger(__name__)

STACK_KEY = "cfg.stack"
SECRETS_KEY = "cfg.secrets"
META_KEY = "cfg.meta"
# См. ``app_settings.PUBLIC_ACCESS_KEY`` — дублируем строку, чтобы не импортировать app_settings (циклы).
_PUBLIC_ACCESS_KEY = "public_access"
_DERIVED_COMPOSE_ENV_KEYS = {"LITELLM_MASTER_KEY"}
_NON_COMPOSE_ENV_KEYS = {"LITELLM_API_KEY", "LOG_REPORT_LLM_API_KEY"}

# Secret detection for upserts: ``stack_registry.is_secret_key`` (single source of truth).


def host_gpu_docker_probe_enabled(merged: dict[str, str]) -> bool:
    """Эфемерный ``docker run`` с GPU для ``nvidia-smi`` (дашборд, gpu/state, DCGM=auto)."""

    raw = (merged.get("HOST_GPU_DOCKER_PROBE") or "on").strip().lower()
    return raw not in ("off", "false", "0", "no", "disabled")


def nvidia_smi_docker_image_for_stack(merged: dict[str, str]) -> str:
    """Образ с ``nvidia-smi`` из стека БД или ``Settings.nvidia_smi_docker_image``."""

    from app.core.config import get_settings

    v = (merged.get("NVIDIA_SMI_DOCKER_IMAGE") or "").strip()
    if v:
        return v
    return get_settings().nvidia_smi_docker_image


def monitoring_dcgm_wanted(merged: dict[str, str], slgpu_root: Path) -> bool:
    """Включить DCGM exporter (compose profile ``gpu``), scrape Prometheus, пробу в UI.

    ``MONITORING_DCGM``: ``auto`` (по умолчанию при отсутствии ключа) | ``on`` | ``off``.
    """
    from app.services.host_info import collect_host_info

    raw = (merged.get("MONITORING_DCGM") or "auto").strip().lower()
    if raw in ("off", "false", "0", "no"):
        return False
    if raw in ("on", "true", "1", "yes"):
        return True
    info = collect_host_info(slgpu_root)
    nv = info.get("nvidia") or {}
    if not nv.get("smi_available"):
        return False
    gpus = nv.get("gpus")
    return isinstance(gpus, list) and len(gpus) > 0


def _prometheus_dcgm_scrape_yaml(merged: dict[str, str]) -> str:
    svc = str(merged.get("DCGM_EXPORTER_SERVICE_NAME") or "").strip()
    port = str(merged.get("DCGM_EXPORTER_INTERNAL_PORT") or "").strip()
    return (
        f'  - job_name: dcgm\n'
        f'    static_configs:\n'
        f'      - targets: ["{svc}:{port}"]\n'
    )


def sqlite_path_from_database_url(url: str) -> Path | None:
    """Сопоставить ``WEB_DATABASE_URL`` с путём к файлу SQLite (не ``:memory:``).

    URL вида ``sqlite+aiosqlite:////data/slgpu-web.db`` (четыре слеша — абсолютный путь в Unix)
    должен давать **абсолютный** путь. Старое регулярное выражение обрезало ведущий ``/`` и
    оставляло ``data/...`` относительно CWD процесса — тогда ``_connect_ro()`` не находил файл
    при работе из ``/srv/app`` и ``sync_merged_flat()`` видел «DB unavailable».
    """
    from sqlalchemy.engine.url import make_url

    try:
        u = make_url(url)
    except Exception:  # noqa: BLE001
        return None
    driver = u.drivername or ""
    if "sqlite" not in driver:
        return None
    raw = (u.database or "").strip()
    if not raw or raw == ":memory:":
        return None
    p = Path(raw)
    if p.is_absolute():
        return p
    candidate = Path("/") / raw
    if candidate.is_file():
        return candidate
    return p


def parse_dotenv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def split_stack_and_secrets(flat: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    stack: dict[str, str] = {}
    secrets: dict[str, str] = {}
    for k, v in flat.items():
        if is_secret_key(k):
            secrets[k] = v
        else:
            stack[k] = v
    return stack, secrets


def _connect_ro() -> sqlite3.Connection | None:
    from app.core.config import get_settings

    p = sqlite_path_from_database_url(get_settings().database_url)
    if p is None or not p.is_file():
        return None
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)


def _load_json_key(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row or row[0] is None:
        return {}
    raw = row[0]
    if isinstance(raw, (bytes, str)):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _load_flat_from_stack_params(conn: sqlite3.Connection) -> dict[str, str] | None:
    if not _table_exists(conn, "stack_params"):
        return None
    cur = conn.execute("SELECT param_key, param_value FROM stack_params")
    rows = cur.fetchall()
    if not rows:
        return None
    return {str(k): str(v) if v is not None else "" for k, v in rows}


def _merge_legacy_public_access_litellm_keys(conn: sqlite3.Connection, merged: dict[str, str]) -> None:
    """Backward-compatible fallback for LiteLLM keys saved before they moved to stack secrets."""
    pa = _load_json_key(conn, _PUBLIC_ACCESS_KEY)
    if not isinstance(pa, dict):
        return
    legacy = {
        "LITELLM_MASTER_KEY": pa.get("litellm_master_key"),
        "LITELLM_API_KEY": pa.get("litellm_api_key"),
    }
    for key, raw in legacy.items():
        if key not in merged and isinstance(raw, str) and raw.strip():
            merged[key] = raw.strip()


def sync_merged_flat() -> dict[str, str]:
    """Merged stack values from SQLite only (no code defaults)."""
    merged: dict[str, str] = {}
    conn = _connect_ro()
    if conn is None:
        raise RuntimeError("stack_params DB is unavailable; configure WEB_DATABASE_URL")
    try:
        from_params = _load_flat_from_stack_params(conn)
        if from_params is not None:
            merged.update(from_params)
        else:
            stack = _load_json_key(conn, STACK_KEY)
            secrets = _load_json_key(conn, SECRETS_KEY)
            if isinstance(stack, dict):
                merged.update({k: str(v) for k, v in stack.items() if v is not None})
            if isinstance(secrets, dict):
                merged.update({k: str(v) for k, v in secrets.items() if v is not None})
        if not merged:
            raise RuntimeError("stack_params is empty; run app-config install from configs/main.env")
        from app.services.env_key_aliases import (
            DEPRECATED_MERGED_DROP_KEYS,
            PRESET_ONLY_KEYS,
        )

        for k in DEPRECATED_MERGED_DROP_KEYS:
            merged.pop(k, None)
        # 8.0.0: модельные ключи задаются ТОЛЬКО в карточке пресета — стек их не отдаёт.
        for k in PRESET_ONLY_KEYS:
            merged.pop(k, None)
        _merge_legacy_public_access_litellm_keys(conn, merged)
    finally:
        conn.close()
    apply_vllm_aliases_to_merged(merged)
    return merged


def compose_service_env_path(
    root: Path, merged: dict[str, str] | None = None
) -> Path:
    """Файл со снимком стека для ``docker compose --env-file`` и ``env_file:`` в monitoring/proxy YAML.

    Путь: ``${WEB_DATA_DIR}/.slgpu/compose-service.env`` (по умолчанию ``data/web/.slgpu/…``), чтобы
    **slgpu-web** мог создать каталог (том ``data/web`` chown в entrypoint), а не ``<repo>/.slgpu`` в корне.

    Заполняется из **БД** в native jobs или из **main.env** в bash (см. ``scripts/_lib.sh``). Не в git (под ``data/``).
    """
    m = merged if merged is not None else sync_merged_flat()
    wdd = m["WEB_DATA_DIR"]
    return (resolve_path_relative(root, wdd) / ".slgpu" / "compose-service.env").resolve()


def write_compose_service_env_file(root: Path, merged: dict[str, str]) -> Path:
    """Записать плоский стек в ``<WEB_DATA_DIR>/.slgpu/compose-service.env`` (права 0600)."""
    p = compose_service_env_path(root, merged)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "\n".join(
            f"{k}={v}"
            for k, v in sorted(merged.items())
            if v is not None
            and k not in _NON_COMPOSE_ENV_KEYS
            and (k in CANONICAL_STACK_KEYS or k in _DERIVED_COMPOSE_ENV_KEYS)
        )
        + "\n"
    )
    p.write_text(body, encoding="utf-8")
    p.chmod(0o600)
    return p


_MONITORING_RENDER_TARGETS: tuple[tuple[str, str], ...] = (
    ("configs/monitoring/prometheus/prometheus.yml.tmpl", "prometheus.yml"),
    ("configs/monitoring/prometheus/prometheus-alerts.yml", "prometheus-alerts.yml"),
    ("configs/monitoring/loki/loki-config.yaml.tmpl", "loki-config.yaml"),
    ("configs/monitoring/promtail/promtail-config.yml.tmpl", "promtail-config.yml"),
    (
        "configs/monitoring/grafana/provisioning/datasources/datasource.yml.tmpl",
        "datasource.yml",
    ),
)


def monitoring_configs_dir(root: Path, merged: dict[str, str] | None = None) -> Path:
    """Каталог отрендеренных конфигов мониторинга (compose монтирует его как :ro)."""
    m = merged if merged is not None else sync_merged_flat()
    wdd = m["WEB_DATA_DIR"]
    return (resolve_path_relative(root, wdd) / ".slgpu" / "monitoring").resolve()


# Дефолтный file_sd для job `vllm-slots` (Prometheus): скрейп host.docker.internal:PORT для всех PORT
# в диапазоне [min, max] включительно. Файл рядом с prometheus.yml задаётся вручную или создаётся
# один раз при `render_monitoring_configs`, если файла ещё нет.
VLLM_SLOTS_FILE_SD_HOST = "host.docker.internal"
VLLM_SLOTS_FILE_SD_PORT_MIN = 8110
VLLM_SLOTS_FILE_SD_PORT_MAX = 8130


def _default_vllm_slots_file_sd_json_text() -> str:
    """JSON для `vllm-slots.json` при первой генерации (мультислотный vLLM на хосте)."""
    import json

    lo, hi = VLLM_SLOTS_FILE_SD_PORT_MIN, VLLM_SLOTS_FILE_SD_PORT_MAX
    targets = [f"{VLLM_SLOTS_FILE_SD_HOST}:{p}" for p in range(lo, hi + 1)]
    payload = [{"targets": targets, "labels": {"engine": "vllm"}}]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _render_template_strict(text: str, mapping: dict[str, str]) -> str:
    """Подставить ``${VAR}`` из ``mapping``; падать при пропусках (KeyError)."""
    from string import Template

    return Template(text).substitute(mapping)


def render_monitoring_configs(root: Path, merged: dict[str, str]) -> Path:
    """Сгенерировать конфиги мониторинга из БД в ``${WEB_DATA_DIR}/.slgpu/monitoring/``.

    Вызывается перед ``monitoring up/restart`` (см. ``native_jobs.py``). Compose монтирует
    каталог как :ro в /etc/prometheus, /etc/loki, /etc/promtail и точечно datasource.yml в Grafana.
    Бывшие статические *.yml/*.yaml удалены из репозитория — единственный источник правды БД.
    """
    out_dir = monitoring_configs_dir(root, merged)
    out_dir.mkdir(parents=True, exist_ok=True)
    for src_rel, dst_name in _MONITORING_RENDER_TARGETS:
        src = (root / src_rel).resolve()
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")
        if src.suffix == ".tmpl":
            tmpl_mapping: dict[str, str] = dict(merged)
            if src_rel == "configs/monitoring/prometheus/prometheus.yml.tmpl":
                want_dcgm = monitoring_dcgm_wanted(merged, root)
                tmpl_mapping["DCGM_SCRAPE_YAML"] = (
                    _prometheus_dcgm_scrape_yaml(merged) if want_dcgm else ""
                )
            try:
                text = _render_template_strict(text, tmpl_mapping)
            except KeyError as exc:  # noqa: PERF203
                missing = exc.args[0] if exc.args else "?"
                raise MissingStackParams([str(missing)], "monitoring_up") from exc
        (out_dir / dst_name).write_text(text, encoding="utf-8")
    # file_sd для job vllm-slots: не перезаписываем существующий файл — порты можно сузить/расширить вручную.
    v_slots = out_dir / "vllm-slots.json"
    if not v_slots.is_file():
        v_slots.write_text(_default_vllm_slots_file_sd_json_text(), encoding="utf-8")
    return out_dir


def resolve_path_relative(root: Path, value: str) -> Path:
    if value.startswith("./"):
        return (root / value[2:]).resolve()
    p = Path(value)
    if p.is_absolute():
        return p
    return (root / value).resolve()


def langfuse_litellm_env_path(
    root: Path, merged: dict[str, str] | None = None
) -> Path:
    """Generated Langfuse API keys for LiteLLM. Lives under **WEB_DATA_DIR** (e.g. ``data/web/``) so
    the slgpuweb user can create it; ``configs/secrets/`` is often host root-only and not writable
    from the web container."""
    wdd = (merged or sync_merged_flat())["WEB_DATA_DIR"]
    return resolve_path_relative(root, wdd) / "secrets" / "langfuse-litellm.env"


def models_dir_sync() -> Path:
    from app.core.config import get_settings

    root = get_settings().slgpu_root
    m = sync_merged_flat()
    return resolve_path_relative(root, m["MODELS_DIR"])


def presets_dir_sync() -> Path:
    from app.core.config import get_settings

    root = get_settings().slgpu_root
    m = sync_merged_flat()
    return resolve_path_relative(root, m["PRESETS_DIR"])


def ports_for_probes_sync() -> dict[str, int | str]:
    m = sync_merged_flat()

    def _i(k: str) -> int:
        try:
            return int(m[k])
        except KeyError as exc:
            raise RuntimeError(f"missing required stack param {k}") from exc

    return {
        "llm_default_vllm_port": _i("LLM_API_PORT"),
        "llm_default_sglang_port": _i("LLM_API_PORT_SGLANG"),
        "grafana_port": _i("GRAFANA_PORT"),
        "prometheus_port": _i("PROMETHEUS_PORT"),
        "langfuse_port": _i("LANGFUSE_PORT"),
        "langfuse_web_internal_port": _i("LANGFUSE_WEB_INTERNAL_PORT"),
        "litellm_port": _i("LITELLM_PORT"),
        "loki_port": _i("LOKI_PORT"),
        "compose_project_infer": m["WEB_COMPOSE_PROJECT_INFER"],
        "compose_project_monitoring": m["WEB_COMPOSE_PROJECT_MONITORING"],
        "compose_project_proxy": m["WEB_COMPOSE_PROJECT_PROXY"],
    }


def meta_installed_sync() -> bool:
    conn = _connect_ro()
    if conn is None:
        return False
    try:
        meta = _load_json_key(conn, META_KEY)
        return bool(meta.get("installed"))
    finally:
        conn.close()


def mask_secrets(secrets: dict[str, Any]) -> dict[str, str]:
    return {k: ("***" if v else "") for k, v in secrets.items()}


async def _stack_param_count(session) -> int:
    from app.models.stack_param import StackParam

    n = await session.scalar(select(func.count()).select_from(StackParam))
    return int(n or 0)


async def _load_sections_from_settings_json(session) -> tuple[dict, dict]:
    from app.models.setting import Setting

    async def _one(key: str) -> dict:
        r = await session.execute(select(Setting).where(Setting.key == key))
        row = r.scalar_one_or_none()
        if row is None:
            return {}
        v = row.value
        return dict(v) if isinstance(v, dict) else {}

    stack = await _one(STACK_KEY)
    secrets = await _one(SECRETS_KEY)
    return stack, secrets


async def load_sections(session) -> tuple[dict, dict, dict]:
    from app.models.setting import Setting

    async def _meta() -> dict:
        r = await session.execute(select(Setting).where(Setting.key == META_KEY))
        row = r.scalar_one_or_none()
        if row is None:
            return {}
        v = row.value
        return dict(v) if isinstance(v, dict) else {}

    from app.models.stack_param import StackParam

    cnt = await _stack_param_count(session)
    if cnt > 0:
        r = await session.execute(select(StackParam))
        rows = r.scalars().all()
        stack: dict[str, str] = {}
        secrets: dict[str, str] = {}
        for row in rows:
            if row.is_secret:
                secrets[row.param_key] = row.param_value
            else:
                stack[row.param_key] = row.param_value
        meta = await _meta()
        return stack, secrets, meta

    stack, secrets = await _load_sections_from_settings_json(session)
    meta = await _meta()
    return stack, secrets, meta


async def save_section(session, key: str, value: dict) -> None:
    from app.models.setting import Setting

    r = await session.execute(select(Setting).where(Setting.key == key))
    row = r.scalar_one_or_none()
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


async def migrate_legacy_json_to_rows(session) -> None:
    from app.models.setting import Setting
    from app.models.stack_param import StackParam

    cnt = await _stack_param_count(session)
    if cnt > 0:
        return

    stack_d, secrets_d = await _load_sections_from_settings_json(session)
    if not stack_d and not secrets_d:
        return

    for k, v in stack_d.items():
        if v is None:
            continue
        session.add(
            StackParam(
                param_key=str(k),
                param_value=str(v),
                is_secret=is_secret_key(str(k)),
            )
        )
    for k, v in secrets_d.items():
        if v is None:
            continue
        key_s = str(k)
        r = await session.execute(select(StackParam).where(StackParam.param_key == key_s))
        existing = r.scalar_one_or_none()
        if existing is not None:
            existing.param_value = str(v)
            existing.is_secret = True
        else:
            session.add(StackParam(param_key=key_s, param_value=str(v), is_secret=True))

    for key in (STACK_KEY, SECRETS_KEY):
        r = await session.execute(select(Setting).where(Setting.key == key))
        row = r.scalar_one_or_none()
        if row is not None:
            row.value = {}
    logger.info(
        "[stack_config][migrate_legacy_json_to_rows][BLOCK_MIGRATED] "
        "legacy cfg.stack/cfg.secrets JSON -> stack_params",
    )


async def ensure_default_settings(session) -> None:
    from app.models.setting import Setting

    for k, default in (
        (STACK_KEY, {}),
        (SECRETS_KEY, {}),
        (META_KEY, {}),
    ):
        r = await session.execute(select(Setting).where(Setting.key == k))
        if r.scalar_one_or_none() is None:
            session.add(Setting(key=k, value=default))
            logger.info("[stack_config] seeded %s", k)


async def log_missing_canonical_keys(session) -> None:
    if await _stack_param_count(session) == 0:
        return
    stack, sec, _ = await load_sections(session)
    merged = {**stack, **sec}
    miss = missing_keys_in_db(merged)
    if miss:
        logger.warning(
            "[stack_config] incomplete stack vs registry (fill in Настройки or install main.env): %s",
            miss[:50],
        )


async def ensure_secret_flags_only(session) -> None:
    """Sync ``is_secret`` on existing rows from ``is_secret_key``; no value inserts."""
    from app.models.stack_param import StackParam

    r = await session.execute(select(StackParam))
    for row in r.scalars().all():
        want = is_secret_key(str(row.param_key))
        if row.is_secret != want:
            row.is_secret = want


async def replace_all_params_from_flat(session, flat: dict[str, str]) -> None:
    from app.models.stack_param import StackParam

    await session.execute(delete(StackParam))
    for k, v in flat.items():
        session.add(
            StackParam(
                param_key=str(k),
                param_value=str(v),
                is_secret=is_secret_key(str(k)),
            )
        )


async def upsert_stack_param(session, key: str, value: str) -> None:
    from app.models.stack_param import StackParam

    is_sec = is_secret_key(key)
    r = await session.execute(select(StackParam).where(StackParam.param_key == key))
    row = r.scalar_one_or_none()
    if row is None:
        session.add(StackParam(param_key=key, param_value=value, is_secret=is_sec))
    else:
        row.param_value = value
        row.is_secret = is_sec


async def delete_stack_param(session, key: str) -> None:
    from app.models.stack_param import StackParam

    await session.execute(delete(StackParam).where(StackParam.param_key == key))


async def _migrate_public_access_litellm_keys_to_stack_secrets(session) -> None:
    """Move LiteLLM secrets from legacy public_access JSON into stack_params secrets."""
    from app.models.setting import Setting

    r = await session.execute(select(Setting).where(Setting.key == _PUBLIC_ACCESS_KEY))
    row = r.scalar_one_or_none()
    if row is None or not isinstance(row.value, dict):
        return

    value = dict(row.value)
    _, secrets, _ = await load_sections(session)
    moved = False
    for legacy_key, stack_key in (
        ("litellm_master_key", "LITELLM_MASTER_KEY"),
        ("litellm_api_key", "LITELLM_API_KEY"),
    ):
        raw = value.get(legacy_key)
        if isinstance(raw, str) and raw.strip() and not str(secrets.get(stack_key, "")).strip():
            await upsert_stack_param(session, stack_key, raw.strip())
            moved = True
        if legacy_key in value and (stack_key in secrets or isinstance(raw, str)):
            value.pop(legacy_key, None)
            moved = True

    if moved:
        row.value = value
        logger.info(
            "[stack_config][migrate_public_access_litellm_keys][BLOCK_MIGRATED] "
            "moved legacy LiteLLM keys to stack secrets"
        )


async def migrate_stack_params_to_canonical_if_needed(session) -> None:
    """Переписать stack_params: убрать устаревшие SLGPU_*-алиасы, оставить канонические имена.

    Один проход при первом обращении к API после обновления 4.2.x; дальше legacy-строк нет.
    """
    from app.services.env_key_aliases import (
        DEPRECATED_MERGED_DROP_KEYS,
        MONITORING_IMAGE_LEGACY_KEYS,
        PRESET_ONLY_KEYS,
        STRIP_VLLM_LEGACY_STACK_KEYS,
        presentation_stack,
    )

    await _migrate_public_access_litellm_keys_to_stack_secrets(session)

    stack, _, _ = await load_sections(session)
    # 8.0.0: помимо устаревших алиасов уносим из stack_params ключи, перенесённые в карточку пресета.
    obsolete_removed = [k for k in (DEPRECATED_MERGED_DROP_KEYS | PRESET_ONLY_KEYS) if k in stack]
    for k in obsolete_removed:
        await delete_stack_param(session, k)
    if obsolete_removed:
        logger.info(
            "[stack_config][migrate_stack_params_to_canonical][BLOCK_removed_obsolete] keys=%s",
            obsolete_removed,
        )

    stack, _, _ = await load_sections(session)
    if not stack:
        return
    legacy = [
        k
        for k in stack
        if k in STRIP_VLLM_LEGACY_STACK_KEYS or k in MONITORING_IMAGE_LEGACY_KEYS
    ]
    if not legacy:
        return
    pres = presentation_stack(stack)
    for k, v in pres.items():
        await upsert_stack_param(session, k, v)
    for k in legacy:
        await delete_stack_param(session, k)
    logger.info(
        "[stack_config][migrate_stack_params_to_canonical][BLOCK_MIGRATED] removed_legacy=%s",
        legacy,
    )


async def replace_secret_params(session, secrets: dict[str, str]) -> None:
    from app.models.stack_param import StackParam

    await session.execute(delete(StackParam).where(StackParam.is_secret.is_(True)))
    for k, v in secrets.items():
        session.add(StackParam(param_key=str(k), param_value=str(v), is_secret=True))


def merge_partial_secrets(
    current: dict[str, str],
    patch: dict[str, str | None],
) -> dict[str, str]:
    out = dict(current)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif v in ("***",):
            continue
        else:
            out[k] = v
    return out


def write_langfuse_litellm_env(
    root: Path, secrets: dict[str, str], merged: dict[str, str] | None = None
) -> None:
    path = langfuse_litellm_env_path(root, merged)
    path.parent.mkdir(parents=True, exist_ok=True)
    pub = str(secrets.get("LANGFUSE_PUBLIC_KEY", "") or "")
    sec = str(secrets.get("LANGFUSE_SECRET_KEY", "") or "")
    text = (
        "# Generated by slgpu-web from DB — do not commit.\n"
        f"LANGFUSE_PUBLIC_KEY={pub}\n"
        f"LANGFUSE_SECRET_KEY={sec}\n"
    )
    path.write_text(text, encoding="utf-8")
    with suppress(OSError):
        path.chmod(0o600)


def _stack_val(m: dict[str, str], key: str) -> str:
    meta = STACK_KEY_REGISTRY.get(key)
    v = m.get(key)
    # 8.0.0: ключ исключён из реестра (например, MODEL_ID/TP/...) — отдаём как есть, без падения.
    if meta is None:
        return "" if v is None else str(v)
    if meta.allow_empty:
        return "" if v is None else str(v)
    if v is None or str(v).strip() == "":
        raise MissingStackParams([key], "llm_interp")
    return str(v)


def write_llm_interp_env(path: Path, merged: dict[str, str]) -> None:
    from app.services.env_key_aliases import coalesce_str

    m = dict(merged)
    apply_vllm_aliases_to_merged(m)

    batch = coalesce_str(
        m,
        "MAX_NUM_BATCHED_TOKENS",
        "SLGPU_MAX_NUM_BATCHED_TOKENS",
        "VLLM_MAX_NUM_BATCHED_TOKENS",
        default="",
    )
    if not str(batch).strip():
        raise MissingStackParams(
            ["MAX_NUM_BATCHED_TOKENS", "SLGPU_MAX_NUM_BATCHED_TOKENS", "VLLM_MAX_NUM_BATCHED_TOKENS"],
            "llm_slot",
        )
    lines = [
        f"VLLM_DOCKER_IMAGE={_stack_val(m, 'VLLM_DOCKER_IMAGE')}",
        f"LLM_API_BIND={_stack_val(m, 'LLM_API_BIND')}",
        f"LLM_API_PORT={_stack_val(m, 'LLM_API_PORT')}",
        f"SLGPU_MODEL_ROOT={_stack_val(m, 'SLGPU_MODEL_ROOT')}",
        f"SERVED_MODEL_NAME={_stack_val(m, 'SERVED_MODEL_NAME')}",
        f"TRUST_REMOTE_CODE={_stack_val(m, 'TRUST_REMOTE_CODE')}",
        f"ENABLE_CHUNKED_PREFILL={_stack_val(m, 'ENABLE_CHUNKED_PREFILL')}",
        f"ENABLE_AUTO_TOOL_CHOICE={_stack_val(m, 'ENABLE_AUTO_TOOL_CHOICE')}",
        f"MODEL_ID={_stack_val(m, 'MODEL_ID')}",
        f"MODEL_REVISION={_stack_val(m, 'MODEL_REVISION')}",
        f"MAX_MODEL_LEN={_stack_val(m, 'MAX_MODEL_LEN')}",
        f"BLOCK_SIZE={_stack_val(m, 'BLOCK_SIZE')}",
        f"TP={_stack_val(m, 'TP')}",
        f"GPU_MEM_UTIL={_stack_val(m, 'GPU_MEM_UTIL')}",
        f"KV_CACHE_DTYPE={_stack_val(m, 'KV_CACHE_DTYPE')}",
        f"MAX_NUM_BATCHED_TOKENS={batch}",
        f"MAX_NUM_SEQS={_stack_val(m, 'MAX_NUM_SEQS')}",
        f"DISABLE_CUSTOM_ALL_REDUCE={_stack_val(m, 'DISABLE_CUSTOM_ALL_REDUCE')}",
        f"ENABLE_PREFIX_CACHING={_stack_val(m, 'ENABLE_PREFIX_CACHING')}",
        f"TOOL_CALL_PARSER={_stack_val(m, 'TOOL_CALL_PARSER')}",
        f"REASONING_PARSER={_stack_val(m, 'REASONING_PARSER')}",
        f"CHAT_TEMPLATE_CONTENT_FORMAT={_stack_val(m, 'CHAT_TEMPLATE_CONTENT_FORMAT')}",
        f"COMPILATION_CONFIG={_stack_val(m, 'COMPILATION_CONFIG')}",
        f"ENFORCE_EAGER={_stack_val(m, 'ENFORCE_EAGER')}",
        f"SPECULATIVE_CONFIG={_stack_val(m, 'SPECULATIVE_CONFIG')}",
        f"ENABLE_EXPERT_PARALLEL={_stack_val(m, 'ENABLE_EXPERT_PARALLEL')}",
        f"DATA_PARALLEL_SIZE={_stack_val(m, 'DATA_PARALLEL_SIZE')}",
        f"MM_ENCODER_TP_MODE={_stack_val(m, 'MM_ENCODER_TP_MODE')}",
        f"ATTENTION_BACKEND={_stack_val(m, 'ATTENTION_BACKEND')}",
        f"TOKENIZER_MODE={_stack_val(m, 'TOKENIZER_MODE')}",
        f"TORCH_FLOAT32_MATMUL_PRECISION={_stack_val(m, 'TORCH_FLOAT32_MATMUL_PRECISION')}",
        f"VLLM_USE_V1={_stack_val(m, 'VLLM_USE_V1')}",
        f"VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS={_stack_val(m, 'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS')}",
        f"NVIDIA_VISIBLE_DEVICES={_stack_val(m, 'NVIDIA_VISIBLE_DEVICES')}",
        f"MODELS_DIR={_stack_val(m, 'MODELS_DIR')}",
        f"SGLANG_TRUST_REMOTE_CODE={_stack_val(m, 'SGLANG_TRUST_REMOTE_CODE')}",
        f"SGLANG_MEM_FRACTION_STATIC={_stack_val(m, 'SGLANG_MEM_FRACTION_STATIC')}",
        f"SGLANG_CUDA_GRAPH_MAX_BS={_stack_val(m, 'SGLANG_CUDA_GRAPH_MAX_BS')}",
        f"SGLANG_ENABLE_TORCH_COMPILE={_stack_val(m, 'SGLANG_ENABLE_TORCH_COMPILE')}",
        f"SGLANG_DISABLE_CUDA_GRAPH={_stack_val(m, 'SGLANG_DISABLE_CUDA_GRAPH')}",
        f"SGLANG_DISABLE_CUSTOM_ALL_REDUCE={_stack_val(m, 'SGLANG_DISABLE_CUSTOM_ALL_REDUCE')}",
        f"SGLANG_ENABLE_METRICS={_stack_val(m, 'SGLANG_ENABLE_METRICS')}",
        f"SGLANG_ENABLE_MFU_METRICS={_stack_val(m, 'SGLANG_ENABLE_MFU_METRICS')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
