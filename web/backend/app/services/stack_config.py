"""Stack configuration in SQLite (web no longer reads main.env at runtime).

``settings`` rows:
- ``cfg.stack`` — non-secret flat env
- ``cfg.secrets`` — secrets (masked in API)
- ``cfg.meta`` — ``{installed, installed_at, source}``
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STACK_KEY = "cfg.stack"
SECRETS_KEY = "cfg.secrets"
META_KEY = "cfg.meta"

SECRET_SUFFIXES = (
    "_PASSWORD",
    "_SECRET",
    "_KEY",
    "_SALT",
    "_TOKEN",
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "NEXTAUTH_SECRET",
    "LANGFUSE_REDIS_AUTH",
)

SECRET_EXACT = frozenset(
    {
        "HF_TOKEN",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_SALT",
        "LANGFUSE_ENCRYPTION_KEY",
        "NEXTAUTH_SECRET",
        "LANGFUSE_POSTGRES_PASSWORD",
        "LANGFUSE_REDIS_AUTH",
        "LANGFUSE_CLICKHOUSE_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "LITELLM_MASTER_KEY",
        "UI_PASSWORD",
        "GRAFANA_ADMIN_PASSWORD",
    }
)


def _is_secret_key(name: str) -> bool:
    if name in SECRET_EXACT:
        return True
    return any(name.endswith(s) for s in SECRET_SUFFIXES)


DEFAULT_STACK: dict[str, str] = {
    "MODELS_DIR": "./data/models",
    "PRESETS_DIR": "./data/presets",
    "WEB_DATA_DIR": "./data/web",
    "SLGPU_MODEL_ROOT": "/models",
    "SLGPU_SERVED_MODEL_NAME": "devllm",
    "LLM_API_BIND": "0.0.0.0",
    "LLM_API_PORT": "8111",
    "LLM_API_PORT_SGLANG": "8222",
    "MAX_MODEL_LEN": "32768",
    "TP": "8",
    "GPU_MEM_UTIL": "0.92",
    "KV_CACHE_DTYPE": "fp8_e4m3",
    "WEB_PORT": "8089",
    "WEB_BIND": "0.0.0.0",
    "WEB_LOG_LEVEL": "INFO",
    "WEB_COMPOSE_PROJECT_INFER": "slgpu",
    "WEB_COMPOSE_PROJECT_MONITORING": "slgpu-monitoring",
    "PROMETHEUS_PORT": "9090",
    "GRAFANA_PORT": "3000",
    "LANGFUSE_PORT": "3001",
    "LITELLM_PORT": "4000",
    "LOKI_PORT": "3100",
    "TOOL_CALL_PARSER": "hermes",
    "REASONING_PARSER": "qwen3",
    "NVIDIA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7",
    "SLGPU_MAX_NUM_BATCHED_TOKENS": "8192",
    "SLGPU_DISABLE_CUSTOM_ALL_REDUCE": "1",
    "SLGPU_ENABLE_PREFIX_CACHING": "1",
    "PROMETHEUS_DATA_DIR": "./data/monitoring/prometheus",
    "GRAFANA_DATA_DIR": "./data/monitoring/grafana",
    "LOKI_DATA_DIR": "./data/monitoring/loki",
    "PROMTAIL_DATA_DIR": "./data/monitoring/promtail",
}


def sqlite_path_from_database_url(url: str) -> Path | None:
    if "sqlite" not in url:
        return None
    m = re.search(r"sqlite\+?[a-z]*:///(?:/)?(.+)", url, re.I)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw == ":memory:" or not raw:
        return None
    return Path(raw)


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
        if _is_secret_key(k):
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


def sync_merged_flat() -> dict[str, str]:
    merged = dict(DEFAULT_STACK)
    conn = _connect_ro()
    if conn is not None:
        try:
            stack = _load_json_key(conn, STACK_KEY)
            secrets = _load_json_key(conn, SECRETS_KEY)
            if isinstance(stack, dict):
                merged.update({k: str(v) for k, v in stack.items() if v is not None})
            if isinstance(secrets, dict):
                merged.update({k: str(v) for k, v in secrets.items() if v is not None})
        finally:
            conn.close()
    return merged


def resolve_path_relative(root: Path, value: str) -> Path:
    if value.startswith("./"):
        return (root / value[2:]).resolve()
    p = Path(value)
    if p.is_absolute():
        return p
    return (root / value).resolve()


def models_dir_sync() -> Path:
    from app.core.config import get_settings

    root = get_settings().slgpu_root
    m = sync_merged_flat()
    md = m.get("MODELS_DIR", "./data/models")
    return resolve_path_relative(root, md)


def presets_dir_sync() -> Path:
    from app.core.config import get_settings

    root = get_settings().slgpu_root
    m = sync_merged_flat()
    pd = m.get("PRESETS_DIR", "./data/presets")
    return resolve_path_relative(root, pd)


def ports_for_probes_sync() -> dict[str, int | str]:
    m = sync_merged_flat()

    def _i(k: str, d: str) -> int:
        try:
            return int(m.get(k, d))
        except ValueError:
            return int(d)

    return {
        "llm_default_vllm_port": _i("LLM_API_PORT", "8111"),
        "llm_default_sglang_port": _i("LLM_API_PORT_SGLANG", "8222"),
        "grafana_port": _i("GRAFANA_PORT", "3000"),
        "prometheus_port": _i("PROMETHEUS_PORT", "9090"),
        "langfuse_port": _i("LANGFUSE_PORT", "3001"),
        "litellm_port": _i("LITELLM_PORT", "4000"),
        "loki_port": _i("LOKI_PORT", "3100"),
        "compose_project_infer": m.get("WEB_COMPOSE_PROJECT_INFER", "slgpu"),
        "compose_project_monitoring": m.get("WEB_COMPOSE_PROJECT_MONITORING", "slgpu-monitoring"),
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


async def load_sections(session) -> tuple[dict, dict, dict]:
    from sqlalchemy import select

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
    meta = await _one(META_KEY)
    return stack, secrets, meta


async def save_section(session, key: str, value: dict) -> None:
    from sqlalchemy import select

    from app.models.setting import Setting

    r = await session.execute(select(Setting).where(Setting.key == key))
    row = r.scalar_one_or_none()
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value


async def ensure_default_settings(session) -> None:
    from sqlalchemy import select

    from app.models.setting import Setting

    for k, default in (
        (STACK_KEY, dict(DEFAULT_STACK)),
        (SECRETS_KEY, {}),
        (META_KEY, {}),
    ):
        r = await session.execute(select(Setting).where(Setting.key == k))
        if r.scalar_one_or_none() is None:
            session.add(Setting(key=k, value=default))
            logger.info("[stack_config] seeded %s", k)


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


def write_langfuse_litellm_env(root: Path, secrets: dict[str, str]) -> None:
    path = root / "configs" / "secrets" / "langfuse-litellm.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    pub = secrets.get("LANGFUSE_PUBLIC_KEY", "")
    sec = secrets.get("LANGFUSE_SECRET_KEY", "")
    text = (
        "# Generated by slgpu-web from DB — do not commit secrets.\n"
        f"LANGFUSE_PUBLIC_KEY={pub}\n"
        f"LANGFUSE_SECRET_KEY={sec}\n"
    )
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def write_llm_interp_env(path: Path, merged: dict[str, str]) -> None:
    def g(key: str, default: str = "") -> str:
        return str(merged.get(key) or default)

    batch = g("SLGPU_MAX_NUM_BATCHED_TOKENS") or g("VLLM_MAX_NUM_BATCHED_TOKENS") or "8192"
    lines = [
        f"VLLM_DOCKER_IMAGE={g('VLLM_DOCKER_IMAGE')}",
        f"LLM_API_BIND={g('LLM_API_BIND', '0.0.0.0')}",
        f"LLM_API_PORT={g('LLM_API_PORT', '8111')}",
        f"SLGPU_MODEL_ROOT={g('SLGPU_MODEL_ROOT', '/models')}",
        f"SLGPU_VLLM_TRUST_REMOTE_CODE={g('SLGPU_VLLM_TRUST_REMOTE_CODE', '1')}",
        f"SLGPU_VLLM_ENABLE_CHUNKED_PREFILL={g('SLGPU_VLLM_ENABLE_CHUNKED_PREFILL', '1')}",
        f"SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE={g('SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE', '1')}",
        f"MODEL_ID={g('MODEL_ID')}",
        f"MODEL_REVISION={g('MODEL_REVISION')}",
        f"MAX_MODEL_LEN={g('MAX_MODEL_LEN', '32768')}",
        f"SLGPU_VLLM_BLOCK_SIZE={g('SLGPU_VLLM_BLOCK_SIZE')}",
        f"TP={g('TP', '8')}",
        f"GPU_MEM_UTIL={g('GPU_MEM_UTIL', '0.92')}",
        f"KV_CACHE_DTYPE={g('KV_CACHE_DTYPE', 'fp8_e4m3')}",
        f"SLGPU_MAX_NUM_BATCHED_TOKENS={batch}",
        f"VLLM_MAX_NUM_BATCHED_TOKENS={g('VLLM_MAX_NUM_BATCHED_TOKENS')}",
        f"SLGPU_VLLM_MAX_NUM_SEQS={g('SLGPU_VLLM_MAX_NUM_SEQS')}",
        f"SLGPU_DISABLE_CUSTOM_ALL_REDUCE={g('SLGPU_DISABLE_CUSTOM_ALL_REDUCE', '1')}",
        f"SLGPU_ENABLE_PREFIX_CACHING={g('SLGPU_ENABLE_PREFIX_CACHING', '1')}",
        f"TOOL_CALL_PARSER={g('TOOL_CALL_PARSER', 'hermes')}",
        f"REASONING_PARSER={g('REASONING_PARSER', 'qwen3')}",
        f"CHAT_TEMPLATE_CONTENT_FORMAT={g('CHAT_TEMPLATE_CONTENT_FORMAT')}",
        f"SLGPU_VLLM_COMPILATION_CONFIG={g('SLGPU_VLLM_COMPILATION_CONFIG')}",
        f"SLGPU_VLLM_ENFORCE_EAGER={g('SLGPU_VLLM_ENFORCE_EAGER', '0')}",
        f"SLGPU_VLLM_SPECULATIVE_CONFIG={g('SLGPU_VLLM_SPECULATIVE_CONFIG')}",
        f"SLGPU_ENABLE_EXPERT_PARALLEL={g('SLGPU_ENABLE_EXPERT_PARALLEL', '0')}",
        f"SLGPU_VLLM_DATA_PARALLEL_SIZE={g('SLGPU_VLLM_DATA_PARALLEL_SIZE')}",
        f"MM_ENCODER_TP_MODE={g('MM_ENCODER_TP_MODE')}",
        f"SLGPU_VLLM_ATTENTION_BACKEND={g('SLGPU_VLLM_ATTENTION_BACKEND')}",
        f"SLGPU_VLLM_TOKENIZER_MODE={g('SLGPU_VLLM_TOKENIZER_MODE')}",
        f"VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS={g('VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS', '1')}",
        f"NVIDIA_VISIBLE_DEVICES={g('NVIDIA_VISIBLE_DEVICES', '0,1,2,3,4,5,6,7')}",
        f"MODELS_DIR={g('MODELS_DIR', './data/models')}",
        f"SGLANG_TRUST_REMOTE_CODE={g('SGLANG_TRUST_REMOTE_CODE', '1')}",
        f"SGLANG_MEM_FRACTION_STATIC={g('SGLANG_MEM_FRACTION_STATIC', '0.90')}",
        f"SGLANG_CUDA_GRAPH_MAX_BS={g('SGLANG_CUDA_GRAPH_MAX_BS')}",
        f"SGLANG_ENABLE_TORCH_COMPILE={g('SGLANG_ENABLE_TORCH_COMPILE', '1')}",
        f"SGLANG_DISABLE_CUDA_GRAPH={g('SGLANG_DISABLE_CUDA_GRAPH', '0')}",
        f"SGLANG_DISABLE_CUSTOM_ALL_REDUCE={g('SGLANG_DISABLE_CUSTOM_ALL_REDUCE', '0')}",
        f"SGLANG_ENABLE_METRICS={g('SGLANG_ENABLE_METRICS', '1')}",
        f"SGLANG_ENABLE_MFU_METRICS={g('SGLANG_ENABLE_MFU_METRICS', '0')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
