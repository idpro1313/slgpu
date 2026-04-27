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

# Образы мониторинга: (каноническое, legacy)
MONITORING_IMAGE_ALIASES: tuple[tuple[str, str], ...] = (
    ("DCGM_EXPORTER_IMAGE", "SLGPU_DCGM_EXPORTER_IMAGE"),
    ("NODE_EXPORTER_IMAGE", "SLGPU_NODE_EXPORTER_IMAGE"),
    ("LOKI_IMAGE", "SLGPU_LOKI_IMAGE"),
    ("PROMTAIL_IMAGE", "SLGPU_PROMTAIL_IMAGE"),
    ("PROMETHEUS_IMAGE", "SLGPU_PROMETHEUS_IMAGE"),
    ("GRAFANA_IMAGE", "SLGPU_GRAFANA_IMAGE"),
    ("LANGFUSE_CLICKHOUSE_IMAGE", "SLGPU_LANGFUSE_CLICKHOUSE_IMAGE"),
    ("MINIO_IMAGE", "SLGPU_MINIO_IMAGE"),
    ("MINIO_MC_IMAGE", "SLGPU_MINIO_MC_IMAGE"),
    ("LANGFUSE_REDIS_IMAGE", "SLGPU_LANGFUSE_REDIS_IMAGE"),
    ("LANGFUSE_POSTGRES_IMAGE", "SLGPU_LANGFUSE_POSTGRES_IMAGE"),
    ("LANGFUSE_WORKER_IMAGE", "SLGPU_LANGFUSE_WORKER_IMAGE"),
    ("LANGFUSE_IMAGE", "SLGPU_LANGFUSE_IMAGE"),
    ("LITELLM_IMAGE", "SLGPU_LITELLM_IMAGE"),
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
    from app.services.stack_errors import MissingStackParams

    for can, leg in MONITORING_IMAGE_ALIASES:
        if can == canonical:
            v = coalesce_str(merged, can, leg, default="")
            if not str(v).strip():
                raise MissingStackParams([can], "fix_perms")
            return v
    v = merged.get(canonical, "")
    if not str(v).strip():
        raise MissingStackParams([canonical], "fix_perms")
    return str(v)


# Ключи-алиасы vLLM, которые убираем из ответа API / из БД после миграции.
# LLM_API_PORT — отдельный параметр (хост), не дублирует VLLM_PORT как строку в stack-only смысле.
STRIP_VLLM_LEGACY_STACK_KEYS: frozenset[str] = frozenset(LEGACY_VLLM_PARAM_KEYS - {"LLM_API_PORT"})

MONITORING_IMAGE_LEGACY_KEYS: frozenset[str] = frozenset(leg for _can, leg in MONITORING_IMAGE_ALIASES)


def presentation_stack(stack: dict[str, str]) -> dict[str, str]:
    """Канонические имена для UI и API: без дублирующих SLGPU_* / legacy для образов."""
    m = {str(k): str(v) if v is not None else "" for k, v in stack.items()}
    apply_vllm_aliases_to_merged(m)
    for can, leg in MONITORING_IMAGE_ALIASES:
        val = coalesce_str(m, can, leg)
        if val:
            m[can] = val
        m.pop(leg, None)
    for k in STRIP_VLLM_LEGACY_STACK_KEYS:
        m.pop(k, None)
    return m

