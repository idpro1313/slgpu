"""Canonical stack key metadata and per-scope required keys (no default values in code)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.services.stack_errors import MissingStackParams

StackScope = Literal[
    "llm_slot",
    "monitoring_up",
    "proxy_up",
    "pull",
    "bench",
    "probes",
    "port_allocation",
    "fix_perms",
]

_SECRET_EXACT = frozenset(
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
_SECRET_SUFFIXES = (
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


def is_secret_key(name: str) -> bool:
    if name in _SECRET_EXACT:
        return True
    return any(name.endswith(s) for s in _SECRET_SUFFIXES)


# Scopes used in compose / native jobs
S_MON: tuple[str, ...] = ("monitoring_up", "proxy_up", "fix_perms")
S_LLM: tuple[str, ...] = ("llm_slot", "bench")
S_ALL_COMPOSE: tuple[str, ...] = ("monitoring_up", "proxy_up")


def _scopes(*names: str) -> frozenset[StackScope]:
    return frozenset(names)  # type: ignore[arg-type]


@dataclass(frozen=True)
class KeyMeta:
    key: str
    group: str
    description: str
    allow_empty: bool
    is_secret: bool
    required_for: frozenset[StackScope]


def _e(
    key: str,
    group: str,
    description: str,
    *req: str,
    allow_empty: bool = False,
) -> KeyMeta:
    return KeyMeta(
        key=key,
        group=group,
        description=description,
        allow_empty=allow_empty,
        is_secret=is_secret_key(key),
        required_for=_scopes(*req) if req else frozenset(),
    )


# --- Registry: every install-time key from main.env; required_for per scope. ---
# New keys (port ranges, SGL listen) are required for llm_slot / port_allocation.
_STACK_KEY_REGISTRY: dict[str, KeyMeta] = {
    "MODELS_DIR": _e("MODELS_DIR", "paths", "Host path to model weights (bind mount).", *S_LLM, *S_ALL_COMPOSE, "pull", "fix_perms"),
    "PRESETS_DIR": _e("PRESETS_DIR", "paths", "Directory of *.env model presets (legacy seed / UI).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "WEB_DATA_DIR": _e("WEB_DATA_DIR", "paths", "Web SQLite and generated secrets/compose env.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SLGPU_MODEL_ROOT": _e("SLGPU_MODEL_ROOT", "paths", "In-container model root (usually /models).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SERVED_MODEL_NAME": _e("SERVED_MODEL_NAME", "inference", "OpenAI API model id exposed to clients.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "LLM_API_BIND": _e("LLM_API_BIND", "llm_api", "Host bind for LLM published port.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "LLM_API_PORT": _e("LLM_API_PORT", "llm_api", "Host port for vLLM mapping.", *S_LLM, *S_ALL_COMPOSE, "probes", "fix_perms"),
    "LLM_API_PORT_SGLANG": _e("LLM_API_PORT_SGLANG", "llm_api", "Host port for SGLang mapping.", *S_LLM, *S_ALL_COMPOSE, "probes", "fix_perms"),
    "MAX_MODEL_LEN": _e("MAX_MODEL_LEN", "inference", "Max context length (tokens).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "TP": _e("TP", "inference", "Tensor-parallel size (default if preset omits).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "GPU_MEM_UTIL": _e("GPU_MEM_UTIL", "inference", "vLLM --gpu-memory-utilization.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "KV_CACHE_DTYPE": _e("KV_CACHE_DTYPE", "inference", "KV cache dtype (vLLM/SGLang).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "WEB_PORT": _e("WEB_PORT", "web", "Published host port for slgpu-web (informational in DB).", *S_ALL_COMPOSE, "fix_perms"),
    "WEB_PUBLIC_HOST": _e(
        "WEB_PUBLIC_HOST",
        "web",
        "Fallback hostname for public URLs when the request has no public hostname (set in main.env; avoid 127.0.0.1 in links).",
        "probes",
        allow_empty=True,
    ),
    "WEB_BIND": _e("WEB_BIND", "web", "slgpu-web bind address (informational).", *S_ALL_COMPOSE, "fix_perms"),
    "SLGPU_HOST_REPO": _e(
        "SLGPU_HOST_REPO",
        "web",
        "Absolute path to slgpu repository on the host (bind mount for slgpu-web / compose).",
        *S_LLM,
        *S_ALL_COMPOSE,
        "fix_perms",
    ),
    "WEB_MONITORING_HTTP_HOST": _e(
        "WEB_MONITORING_HTTP_HOST",
        "web",
        "Host to probe monitoring services from slgpu-web (e.g. host.docker.internal).",
        *S_ALL_COMPOSE,
        "probes",
        "fix_perms",
        allow_empty=True,
    ),
    "WEB_LLM_HTTP_HOST": _e(
        "WEB_LLM_HTTP_HOST",
        "web",
        "Host to probe LLM /metrics and /v1/models from slgpu-web.",
        *S_ALL_COMPOSE,
        "probes",
        "fix_perms",
        allow_empty=True,
    ),
    "SLGPU_ENGINE": _e(
        "SLGPU_ENGINE",
        "inference",
        "vllm|sglang (serve.sh; manual compose llm).",
        *S_LLM,
        *S_ALL_COMPOSE,
        "fix_perms",
    ),
    "UI_USERNAME": _e("UI_USERNAME", "proxy", "LiteLLM Admin UI user.", *S_MON, allow_empty=True),
    "UI_PASSWORD": _e("UI_PASSWORD", "proxy", "LiteLLM Admin UI password.", *S_MON, allow_empty=True),
    "LITELLM_LOG": _e("LITELLM_LOG", "proxy", "LiteLLM log level (e.g. DEBUG for --detailed_debug).", *S_MON, allow_empty=True),
    "LITELLM_LLM_ID": _e("LITELLM_LLM_ID", "proxy", "LiteLLM default LLM / route hint (optional).", *S_MON, allow_empty=True),
    "VLLM_LOGGING_LEVEL": _e(
        "VLLM_LOGGING_LEVEL",
        "inference",
        "VLLM_LOGGING_LEVEL passed into engine containers (optional).",
        *S_LLM,
        *S_ALL_COMPOSE,
        "fix_perms",
        allow_empty=True,
    ),
    "WEB_LOG_LEVEL": _e("WEB_LOG_LEVEL", "web", "Uvicorn log level (informational).", *S_ALL_COMPOSE, "fix_perms"),
    "WEB_COMPOSE_PROJECT_INFER": _e("WEB_COMPOSE_PROJECT_INFER", "compose", "Compose project for LLM stack (llm.yml).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "WEB_COMPOSE_PROJECT_MONITORING": _e("WEB_COMPOSE_PROJECT_MONITORING", "compose", "Compose project: metrics/logs.", *S_ALL_COMPOSE, "probes", "fix_perms"),
    "WEB_COMPOSE_PROJECT_PROXY": _e("WEB_COMPOSE_PROJECT_PROXY", "compose", "Compose project: Langfuse/LiteLLM.", *S_ALL_COMPOSE, "probes", "fix_perms"),
    "DCGM_BIND": _e("DCGM_BIND", "monitoring", "Bind for DCGM exporter.", *S_MON),
    "NODE_EXPORTER_BIND": _e("NODE_EXPORTER_BIND", "monitoring", "Bind for node-exporter.", *S_MON),
    "PROMETHEUS_BIND": _e("PROMETHEUS_BIND", "monitoring", "Bind for Prometheus UI.", *S_MON),
    "PROMETHEUS_PORT": _e("PROMETHEUS_PORT", "monitoring", "Prometheus port.", *S_MON, "probes", "fix_perms"),
    "GRAFANA_BIND": _e("GRAFANA_BIND", "monitoring", "Bind for Grafana.", *S_MON),
    "GRAFANA_PORT": _e("GRAFANA_PORT", "monitoring", "Grafana port.", *S_MON, "probes", "fix_perms"),
    "LANGFUSE_BIND": _e("LANGFUSE_BIND", "proxy", "Bind for Langfuse UI.", *S_MON, "fix_perms"),
    "LANGFUSE_PORT": _e("LANGFUSE_PORT", "proxy", "Langfuse UI port.", *S_MON, "probes", "fix_perms"),
    "LITELLM_BIND": _e("LITELLM_BIND", "proxy", "Bind for LiteLLM proxy.", *S_MON, "fix_perms"),
    "LITELLM_PORT": _e("LITELLM_PORT", "proxy", "LiteLLM port.", *S_MON, "probes", "fix_perms"),
    "LOKI_PORT": _e("LOKI_PORT", "monitoring", "Loki port.", *S_MON, "probes", "fix_perms"),
    "LOKI_BIND": _e("LOKI_BIND", "monitoring", "Bind for Loki.", *S_MON, "fix_perms"),
    "MINIO_API_BIND": _e("MINIO_API_BIND", "proxy", "MinIO API bind.", *S_MON, "fix_perms"),
    "MINIO_API_HOST_PORT": _e("MINIO_API_HOST_PORT", "proxy", "MinIO API host port.", *S_MON, "fix_perms"),
    "MINIO_CONSOLE_BIND": _e("MINIO_CONSOLE_BIND", "proxy", "MinIO console bind.", *S_MON, "fix_perms"),
    "MINIO_CONSOLE_HOST_PORT": _e("MINIO_CONSOLE_HOST_PORT", "proxy", "MinIO console port.", *S_MON, "fix_perms"),
    "LANGFUSE_WORKER_BIND": _e("LANGFUSE_WORKER_BIND", "proxy", "Langfuse worker bind.", *S_MON, "fix_perms"),
    "LANGFUSE_WORKER_PORT": _e("LANGFUSE_WORKER_PORT", "proxy", "Langfuse worker port.", *S_MON, "fix_perms"),
    "TOOL_CALL_PARSER": _e("TOOL_CALL_PARSER", "inference", "Tool-call parser (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "REASONING_PARSER": _e("REASONING_PARSER", "inference", "Reasoning parser.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "NVIDIA_VISIBLE_DEVICES": _e("NVIDIA_VISIBLE_DEVICES", "inference", "GPU device indices (default mask).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "MAX_NUM_BATCHED_TOKENS": _e("MAX_NUM_BATCHED_TOKENS", "inference", "vLLM max batched tokens.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "DISABLE_CUSTOM_ALL_REDUCE": _e("DISABLE_CUSTOM_ALL_REDUCE", "inference", "1=disable custom all-reduce (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "ENABLE_PREFIX_CACHING": _e("ENABLE_PREFIX_CACHING", "inference", "Prefix caching flag.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "ENABLE_EXPERT_PARALLEL": _e("ENABLE_EXPERT_PARALLEL", "inference", "Expert parallelism (MoE).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "VLLM_HOST": _e("VLLM_HOST", "inference", "HTTP listen in vLLM container.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "VLLM_PORT": _e("VLLM_PORT", "inference", "HTTP port in vLLM container.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "TRUST_REMOTE_CODE": _e("TRUST_REMOTE_CODE", "inference", "1=--trust-remote-code (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "ENABLE_CHUNKED_PREFILL": _e("ENABLE_CHUNKED_PREFILL", "inference", "Chunked prefill (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "ENABLE_AUTO_TOOL_CHOICE": _e("ENABLE_AUTO_TOOL_CHOICE", "inference", "Auto tool choice (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "PROMETHEUS_DATA_DIR": _e("PROMETHEUS_DATA_DIR", "monitoring", "Prometheus TSDB on host.", *S_MON, "fix_perms"),
    "GRAFANA_DATA_DIR": _e("GRAFANA_DATA_DIR", "monitoring", "Grafana data on host.", *S_MON, "fix_perms"),
    "LOKI_DATA_DIR": _e("LOKI_DATA_DIR", "monitoring", "Loki data on host.", *S_MON, "fix_perms"),
    "PROMTAIL_DATA_DIR": _e("PROMTAIL_DATA_DIR", "monitoring", "Promtail positions on host.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_DATA_DIR": _e("LANGFUSE_POSTGRES_DATA_DIR", "proxy", "Postgres data for Langfuse/LiteLLM.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_DATA_DIR": _e("LANGFUSE_CLICKHOUSE_DATA_DIR", "proxy", "ClickHouse data.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_LOGS_DIR": _e("LANGFUSE_CLICKHOUSE_LOGS_DIR", "proxy", "ClickHouse logs on host.", *S_MON, "fix_perms"),
    "LANGFUSE_MINIO_DATA_DIR": _e("LANGFUSE_MINIO_DATA_DIR", "proxy", "MinIO data on host.", *S_MON, "fix_perms"),
    "LANGFUSE_REDIS_DATA_DIR": _e("LANGFUSE_REDIS_DATA_DIR", "proxy", "Redis data on host.", *S_MON, "fix_perms"),
    "PROMETHEUS_RETENTION_TIME": _e("PROMETHEUS_RETENTION_TIME", "monitoring", "Prometheus retention time flag.", *S_MON, "fix_perms"),
    "PROMETHEUS_RETENTION_SIZE": _e("PROMETHEUS_RETENTION_SIZE", "monitoring", "Prometheus retention size flag.", *S_MON, "fix_perms"),
    "DCGM_EXPORTER_IMAGE": _e("DCGM_EXPORTER_IMAGE", "monitoring", "DCGM exporter image.", *S_MON, "fix_perms"),
    "NODE_EXPORTER_IMAGE": _e("NODE_EXPORTER_IMAGE", "monitoring", "Node exporter image.", *S_MON, "fix_perms"),
    "LOKI_IMAGE": _e("LOKI_IMAGE", "monitoring", "Loki image.", *S_MON, "fix_perms"),
    "PROMTAIL_IMAGE": _e("PROMTAIL_IMAGE", "monitoring", "Promtail image.", *S_MON, "fix_perms"),
    "PROMETHEUS_IMAGE": _e("PROMETHEUS_IMAGE", "monitoring", "Prometheus image.", *S_MON, "fix_perms"),
    "GRAFANA_IMAGE": _e("GRAFANA_IMAGE", "monitoring", "Grafana image.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_IMAGE": _e("LANGFUSE_CLICKHOUSE_IMAGE", "proxy", "ClickHouse image.", *S_MON, "fix_perms"),
    "MINIO_IMAGE": _e("MINIO_IMAGE", "proxy", "MinIO image.", *S_MON, "fix_perms"),
    "MINIO_MC_IMAGE": _e("MINIO_MC_IMAGE", "proxy", "MinIO mc image.", *S_MON, "fix_perms"),
    "LANGFUSE_REDIS_IMAGE": _e("LANGFUSE_REDIS_IMAGE", "proxy", "Redis image.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_IMAGE": _e("LANGFUSE_POSTGRES_IMAGE", "proxy", "Postgres image (Langfuse/LiteLLM).", *S_MON, "fix_perms"),
    "LANGFUSE_WORKER_IMAGE": _e("LANGFUSE_WORKER_IMAGE", "proxy", "Langfuse worker image.", *S_MON, "fix_perms"),
    "LANGFUSE_IMAGE": _e("LANGFUSE_IMAGE", "proxy", "Langfuse web image.", *S_MON, "fix_perms"),
    "LITELLM_IMAGE": _e("LITELLM_IMAGE", "proxy", "LiteLLM image.", *S_MON, "fix_perms"),
    "GRAFANA_ADMIN_USER": _e("GRAFANA_ADMIN_USER", "monitoring", "Grafana admin user.", *S_MON, "fix_perms"),
    "GRAFANA_ADMIN_PASSWORD": _e("GRAFANA_ADMIN_PASSWORD", "monitoring", "Grafana admin password.", *S_MON, "fix_perms"),
    "GF_SERVER_ROOT_URL": _e("GF_SERVER_ROOT_URL", "monitoring", "Grafana root URL (can be empty for local).", *S_MON, "fix_perms", allow_empty=True),
    "LANGFUSE_CLICKHOUSE_USER": _e("LANGFUSE_CLICKHOUSE_USER", "proxy", "ClickHouse user.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_PASSWORD": _e("LANGFUSE_CLICKHOUSE_PASSWORD", "proxy", "ClickHouse password.", *S_MON, "fix_perms"),
    "MINIO_ROOT_USER": _e("MINIO_ROOT_USER", "proxy", "MinIO root user.", *S_MON, "fix_perms"),
    "MINIO_ROOT_PASSWORD": _e("MINIO_ROOT_PASSWORD", "proxy", "MinIO root password.", *S_MON, "fix_perms"),
    "LANGFUSE_REDIS_AUTH": _e("LANGFUSE_REDIS_AUTH", "proxy", "Redis password.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_USER": _e("LANGFUSE_POSTGRES_USER", "proxy", "Postgres user.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_PASSWORD": _e("LANGFUSE_POSTGRES_PASSWORD", "proxy", "Postgres password.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_DB": _e("LANGFUSE_POSTGRES_DB", "proxy", "Postgres database name (Langfuse).", *S_MON, "fix_perms"),
    "NEXTAUTH_URL": _e("NEXTAUTH_URL", "proxy", "Langfuse NextAuth URL.", *S_MON, "fix_perms"),
    "NEXTAUTH_SECRET": _e("NEXTAUTH_SECRET", "proxy", "NextAuth secret.", *S_MON, "fix_perms"),
    "LANGFUSE_SALT": _e("LANGFUSE_SALT", "proxy", "Langfuse salt.", *S_MON, "fix_perms"),
    "LANGFUSE_ENCRYPTION_KEY": _e("LANGFUSE_ENCRYPTION_KEY", "proxy", "Langfuse encryption key.", *S_MON, "fix_perms"),
    "LANGFUSE_TELEMETRY": _e("LANGFUSE_TELEMETRY", "proxy", "Langfuse telemetry on/off.", *S_MON, "fix_perms"),
    "LANGFUSE_S3_EVENT_UPLOAD_BUCKET": _e("LANGFUSE_S3_EVENT_UPLOAD_BUCKET", "proxy", "MinIO bucket (events).", *S_MON, "fix_perms"),
    "LANGFUSE_S3_MEDIA_BUCKET": _e("LANGFUSE_S3_MEDIA_BUCKET", "proxy", "MinIO bucket (media).", *S_MON, "fix_perms"),
    "LITELLM_POSTGRES_DB": _e("LITELLM_POSTGRES_DB", "proxy", "LiteLLM database name in Postgres.", *S_MON, "fix_perms"),
    "LITELLM_MASTER_KEY": _e("LITELLM_MASTER_KEY", "proxy", "LiteLLM master key (can be overridden from UI).", *S_MON, "fix_perms", allow_empty=True),
    "STORE_MODEL_IN_DB": _e("STORE_MODEL_IN_DB", "proxy", "LiteLLM store model in DB flag.", *S_MON, "fix_perms"),
    "VLLM_DOCKER_IMAGE": _e("VLLM_DOCKER_IMAGE", "inference", "vLLM OpenAI image for slots.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_DOCKER_IMAGE": _e("SGLANG_DOCKER_IMAGE", "inference", "SGLang image for slots.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_TRUST_REMOTE_CODE": _e("SGLANG_TRUST_REMOTE_CODE", "inference", "SGLang trust remote code.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_MEM_FRACTION_STATIC": _e("SGLANG_MEM_FRACTION_STATIC", "inference", "SGLang mem fraction static.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_CUDA_GRAPH_MAX_BS": _e("SGLANG_CUDA_GRAPH_MAX_BS", "inference", "SGLang cuda graph max batch size.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "SGLANG_ENABLE_TORCH_COMPILE": _e("SGLANG_ENABLE_TORCH_COMPILE", "inference", "SGLang torch compile flag.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_DISABLE_CUDA_GRAPH": _e("SGLANG_DISABLE_CUDA_GRAPH", "inference", "SGLang disable cuda graph.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_DISABLE_CUSTOM_ALL_REDUCE": _e("SGLANG_DISABLE_CUSTOM_ALL_REDUCE", "inference", "SGLang disable custom all-reduce.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_ENABLE_METRICS": _e("SGLANG_ENABLE_METRICS", "inference", "SGLang enable metrics.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_ENABLE_MFU_METRICS": _e("SGLANG_ENABLE_MFU_METRICS", "inference", "SGLang MFU metrics.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_LISTEN_HOST": _e("SGLANG_LISTEN_HOST", "inference", "SGLang HTTP listen (container).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SGLANG_LISTEN_PORT": _e("SGLANG_LISTEN_PORT", "inference", "SGLang internal HTTP port (container).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "MODEL_ID": _e("MODEL_ID", "inference", "Hugging Face model id (often overridden by preset).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "MODEL_REVISION": _e("MODEL_REVISION", "inference", "Optional model revision (git/sha).", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "LLM_HOST_PORT_RANGE_VLLM_START": _e("LLM_HOST_PORT_RANGE_VLLM_START", "inference", "First host port in auto-range for vLLM slots.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_VLLM_END": _e("LLM_HOST_PORT_RANGE_VLLM_END", "inference", "Last host port in auto-range for vLLM slots.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_SGLANG_START": _e("LLM_HOST_PORT_RANGE_SGLANG_START", "inference", "First host port in auto-range for SGLang slots.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_SGLANG_END": _e("LLM_HOST_PORT_RANGE_SGLANG_END", "inference", "Last host port in auto-range for SGLang slots.", *S_LLM, "port_allocation"),
    "HF_TOKEN": _e("HF_TOKEN", "secrets", "HuggingFace token (optional for public models).", "pull", allow_empty=True),
    "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": _e(
        "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS", "inference", "vLLM memory profiler flag.", *S_LLM, *S_ALL_COMPOSE, "fix_perms"
    ),
    "LANGFUSE_PUBLIC_KEY": _e("LANGFUSE_PUBLIC_KEY", "proxy", "Langfuse public key for LiteLLM env file.", *S_MON, allow_empty=True),
    "LANGFUSE_SECRET_KEY": _e("LANGFUSE_SECRET_KEY", "proxy", "Langfuse secret key for LiteLLM env file.", *S_MON, allow_empty=True),
    "BLOCK_SIZE": _e("BLOCK_SIZE", "inference", "Optional vLLM block size.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "MAX_NUM_SEQS": _e("MAX_NUM_SEQS", "inference", "Optional vLLM max num seqs.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "CHAT_TEMPLATE_CONTENT_FORMAT": _e("CHAT_TEMPLATE_CONTENT_FORMAT", "inference", "Optional chat template format.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "COMPILATION_CONFIG": _e("COMPILATION_CONFIG", "inference", "Optional vLLM compilation config JSON.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "ENFORCE_EAGER": _e("ENFORCE_EAGER", "inference", "1=--enforce-eager (vLLM).", *S_LLM, *S_ALL_COMPOSE, "fix_perms"),
    "SPECULATIVE_CONFIG": _e("SPECULATIVE_CONFIG", "inference", "Optional speculative decoding config.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "DATA_PARALLEL_SIZE": _e("DATA_PARALLEL_SIZE", "inference", "Optional data-parallel size.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "MM_ENCODER_TP_MODE": _e("MM_ENCODER_TP_MODE", "inference", "Optional mm encoder TP mode.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "ATTENTION_BACKEND": _e("ATTENTION_BACKEND", "inference", "Optional vLLM attention backend.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "TOKENIZER_MODE": _e("TOKENIZER_MODE", "inference", "Optional vLLM tokenizer mode.", *S_LLM, *S_ALL_COMPOSE, "fix_perms", allow_empty=True),
    "SLGPU_BENCH_CHOWN_IMAGE": _e(
        "SLGPU_BENCH_CHOWN_IMAGE",
        "inference",
        "Image for chown in fix-perms (default alpine).",
        "fix_perms",
    ),
}

CANONICAL_STACK_KEYS: frozenset[str] = frozenset(_STACK_KEY_REGISTRY.keys())

STACK_KEY_REGISTRY: dict[str, KeyMeta] = _STACK_KEY_REGISTRY


class MissingKeyInfo(TypedDict):
    key: str
    group: str
    description: str


def _non_empty(s: str | None) -> bool:
    if s is None:
        return False
    return str(s).strip() != ""


def validate_required(merged: dict[str, str], scope: StackScope) -> list[MissingKeyInfo]:
    out: list[MissingKeyInfo] = []
    for key, meta in STACK_KEY_REGISTRY.items():
        if scope not in meta.required_for:
            continue
        v = merged.get(key)
        if meta.allow_empty:
            continue
        if not _non_empty(v):
            out.append(
                {
                    "key": key,
                    "group": meta.group,
                    "description": meta.description,
                }
            )
    return out


def raise_if_missing(merged: dict[str, str], scope: StackScope) -> None:
    missing = validate_required(merged, scope)
    if missing:
        raise MissingStackParams([m["key"] for m in missing], scope)


def missing_keys_in_db(merged: dict[str, str]) -> list[str]:
    """Keys in registry with no value (for startup WARN), respecting allow_empty."""
    out: list[str] = []
    for k in CANONICAL_STACK_KEYS:
        meta = STACK_KEY_REGISTRY.get(k)
        if meta and meta.allow_empty:
            continue
        if not _non_empty(merged.get(k)):
            out.append(k)
    return out


def registry_to_public() -> list[dict[str, Any]]:
    return [
        {
            "key": m.key,
            "group": m.group,
            "description": m.description,
            "is_secret": m.is_secret,
            "allow_empty": m.allow_empty,
            "required_for": sorted(m.required_for),
        }
        for m in sorted(STACK_KEY_REGISTRY.values(), key=lambda x: x.key)
    ]


__all__ = [
    "CANONICAL_STACK_KEYS",
    "KeyMeta",
    "MissingKeyInfo",
    "STACK_KEY_REGISTRY",
    "StackScope",
    "is_secret_key",
    "missing_keys_in_db",
    "raise_if_missing",
    "registry_to_public",
    "validate_required",
]
