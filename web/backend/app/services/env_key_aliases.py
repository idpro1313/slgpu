"""Канонические имена переменных для vLLM/мониторинга; устаревшие SLGPU_* — алиасы.

Читатели окружения подставляют сначала каноническое имя, затем legacy (см. serve.sh, stack_config).
"""

from __future__ import annotations

# (canonical, legacy1, legacy2, …) — порядок при coalesce
VLLM_STACK_ALIASES: tuple[tuple[str, ...], ...] = (
    ("SERVED_MODEL_NAME", "SLGPU_SERVED_MODEL_NAME"),
    ("VLLM_HOST", "SLGPU_VLLM_HOST"),
    ("VLLM_PORT", "SLGPU_VLLM_PORT", "LLM_API_PORT"),
    ("TRUST_REMOTE_CODE", "SLGPU_VLLM_TRUST_REMOTE_CODE"),
    ("ENABLE_CHUNKED_PREFILL", "SLGPU_VLLM_ENABLE_CHUNKED_PREFILL"),
    ("ENABLE_AUTO_TOOL_CHOICE", "SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE"),
    ("MAX_NUM_BATCHED_TOKENS", "SLGPU_MAX_NUM_BATCHED_TOKENS", "VLLM_MAX_NUM_BATCHED_TOKENS"),
    ("MAX_NUM_SEQS", "SLGPU_VLLM_MAX_NUM_SEQS"),
    ("BLOCK_SIZE", "SLGPU_VLLM_BLOCK_SIZE"),
    ("DISABLE_CUSTOM_ALL_REDUCE", "SLGPU_DISABLE_CUSTOM_ALL_REDUCE"),
    ("ENABLE_PREFIX_CACHING", "SLGPU_ENABLE_PREFIX_CACHING"),
    ("ENABLE_EXPERT_PARALLEL", "SLGPU_ENABLE_EXPERT_PARALLEL"),
    ("COMPILATION_CONFIG", "SLGPU_VLLM_COMPILATION_CONFIG"),
    ("ENFORCE_EAGER", "SLGPU_VLLM_ENFORCE_EAGER"),
    ("SPECULATIVE_CONFIG", "SLGPU_VLLM_SPECULATIVE_CONFIG"),
    ("DATA_PARALLEL_SIZE", "SLGPU_VLLM_DATA_PARALLEL_SIZE"),
    ("ATTENTION_BACKEND", "SLGPU_VLLM_ATTENTION_BACKEND"),
    ("TOKENIZER_MODE", "SLGPU_VLLM_TOKENIZER_MODE"),
)


def _legacy_vllm_keys() -> frozenset[str]:
    s: set[str] = set()
    for chain in VLLM_STACK_ALIASES:
        for k in chain[1:]:
            s.add(k)
    return frozenset(s)


LEGACY_VLLM_PARAM_KEYS: frozenset[str] = _legacy_vllm_keys()

# Образы мониторинга: (каноническое, legacy, дефолт для fix-perms — как в native_jobs до рефакторинга)
MONITORING_IMAGE_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("DCGM_EXPORTER_IMAGE", "SLGPU_DCGM_EXPORTER_IMAGE", "nvidia/dcgm-exporter:3.3.5-3.4.0-ubuntu22.04"),
    ("NODE_EXPORTER_IMAGE", "SLGPU_NODE_EXPORTER_IMAGE", "prom/node-exporter:v1.8.2"),
    ("LOKI_IMAGE", "SLGPU_LOKI_IMAGE", "grafana/loki:2.9.8"),
    ("PROMTAIL_IMAGE", "SLGPU_PROMTAIL_IMAGE", "grafana/promtail:2.9.8"),
    ("PROMETHEUS_IMAGE", "SLGPU_PROMETHEUS_IMAGE", "prom/prometheus:v2.55.1"),
    ("GRAFANA_IMAGE", "SLGPU_GRAFANA_IMAGE", "grafana/grafana:11.3.0"),
    ("LANGFUSE_CLICKHOUSE_IMAGE", "SLGPU_LANGFUSE_CLICKHOUSE_IMAGE", "clickhouse/clickhouse-server:24.3"),
    ("MINIO_IMAGE", "SLGPU_MINIO_IMAGE", "minio/minio:RELEASE.2024-11-07T00-52-20Z"),
    ("MINIO_MC_IMAGE", "SLGPU_MINIO_MC_IMAGE", "minio/mc:latest"),
    ("LANGFUSE_REDIS_IMAGE", "SLGPU_LANGFUSE_REDIS_IMAGE", "redis:7"),
    ("LANGFUSE_POSTGRES_IMAGE", "SLGPU_LANGFUSE_POSTGRES_IMAGE", "postgres:17.4"),
    ("LANGFUSE_WORKER_IMAGE", "SLGPU_LANGFUSE_WORKER_IMAGE", "langfuse/langfuse-worker:3"),
    ("LANGFUSE_IMAGE", "SLGPU_LANGFUSE_IMAGE", "langfuse/langfuse:3"),
    ("LITELLM_IMAGE", "SLGPU_LITELLM_IMAGE", "ghcr.io/berriai/litellm:main-latest"),
)


def coalesce_str(m: dict[str, str], *keys: str, default: str = "") -> str:
    for k in keys:
        v = m.get(k)
        if v is not None and str(v).strip() != "":
            return str(v)
    return default


def apply_vllm_aliases_to_merged(merged: dict[str, str]) -> None:
    """Дополняет merged каноническими ключами из первой непустой в цепочке."""
    for chain in VLLM_STACK_ALIASES:
        canonical = chain[0]
        legacies = chain[1:]
        val = coalesce_str(merged, canonical, *legacies)
        if val:
            merged[canonical] = val


def monitoring_image(merged: dict[str, str], canonical: str) -> str:
    for can, leg, dfl in MONITORING_IMAGE_ALIASES:
        if can == canonical:
            return coalesce_str(merged, can, leg, default=dfl) or dfl
    return merged.get(canonical, "") or ""

