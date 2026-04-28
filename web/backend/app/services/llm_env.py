"""Merge stack + preset into env for vLLM/SGLang (compose or docker run)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.env_key_aliases import (
    PRESET_ONLY_KEYS,
    apply_vllm_aliases_to_merged,
    coalesce_str,
)
from app.services.preset_db_sync import load_preset_flat_from_db_sync
from app.services.stack_config import sync_merged_flat
from app.services.stack_errors import MissingStackParams

# Пресет ОБЯЗАН задать эти ключи — иначе слот стартовать нельзя:
# vLLM/SGLang без них сваливаются в дефолты (TP=8 при двух GPU, MAX_MODEL_LEN, …) или вообще не стартуют.
# SERVED_MODEL_NAME / MODEL_REVISION — опциональны (fallback на MODEL_ID / main ветку HF).
PRESET_REQUIRED_KEYS: tuple[str, ...] = ("MODEL_ID", "MAX_MODEL_LEN", "TP", "GPU_MEM_UTIL")


def parse_gpu_mask(value: str | None) -> list[int] | None:
    """Parse PRESET/DB gpu_mask: comma-separated non-negative int GPU indices."""
    if not (value and str(value).strip()):
        return None
    out: list[int] = []
    for part in re.split(r"[\s,;]+", str(value).strip()):
        if not part:
            continue
        try:
            i = int(part)
        except ValueError:
            return None
        if i < 0:
            return None
        out.append(i)
    return out if out else None


def merge_llm_stack_env(
    root: Path,
    merged: dict[str, str],
    preset: str,
    engine: str,
    port: int | None,
    tp: int | None,
    gpu_indices: list[int] | None = None,
) -> dict[str, str]:
    """Return merged key/value env for the LLM container (string values).

    The ``gpu_indices`` list, when provided, sets ``NVIDIA_VISIBLE_DEVICES`` and
    ``TP`` to ``len(gpu_indices)`` (and overrides 0..TP-1 heuristics).
    """
    m: dict[str, str] = dict(merged)
    pextra = load_preset_flat_from_db_sync(preset)
    if pextra is None:
        raise MissingStackParams([f"PRESET:{preset}"], "llm_slot")
    # 8.0.0: значения «модель/инференс» берём ТОЛЬКО из пресета (см. PRESET_ONLY_KEYS).
    # Стек больше не подсовывает старые SLGPU_ENGINE / MODEL_ID / TP / … из main.env,
    # иначе вместо актуального пресета slot ушёл бы с дефолтами «Qwen2.5-0.5B-Instruct», TP=8 и т.п.
    for k in PRESET_ONLY_KEYS:
        m.pop(k, None)
    m.update(pextra)
    missing_preset = [k for k in PRESET_REQUIRED_KEYS if not str(m.get(k, "")).strip()]
    if missing_preset:
        raise MissingStackParams([f"PRESET:{k}" for k in missing_preset], "preset")
    if tp is not None:
        m["TP"] = str(tp)
    if gpu_indices is not None and len(gpu_indices) > 0:
        m["TP"] = str(len(gpu_indices))
        m["NVIDIA_VISIBLE_DEVICES"] = ",".join(str(i) for i in gpu_indices)
    else:
        override_nv = m.get("SLGPU_NVIDIA_VISIBLE_DEVICES", "").strip()
        if override_nv:
            m["NVIDIA_VISIBLE_DEVICES"] = override_nv
        else:
            tpi = int(m["TP"])
            m["NVIDIA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(max(1, tpi)))
    if port is not None:
        m["LLM_API_PORT"] = str(port)
    elif engine == "sglang" and "LLM_API_PORT" not in m:
        m["LLM_API_PORT"] = m["LLM_API_PORT_SGLANG"]
    apply_vllm_aliases_to_merged(m)
    return m


def merged_flat() -> dict[str, str]:
    return sync_merged_flat()


def container_env_for_engine(merged: dict[str, str], engine: str) -> dict[str, str]:
    """Build env for ``scripts/serve.sh`` (flat string dict)."""
    m: dict[str, str] = dict(merged)
    apply_vllm_aliases_to_merged(m)
    m["SLGPU_ENGINE"] = engine
    if engine == "vllm":
        p = coalesce_str(m, "LLM_API_PORT", "SLGPU_VLLM_PORT", default="")
        if not str(p).strip():
            raise MissingStackParams(["LLM_API_PORT"], "llm_slot")
    else:
        p = coalesce_str(m, "LLM_API_PORT_SGLANG", "SGLANG_LISTEN", default="")
        if not str(p).strip():
            raise MissingStackParams(["LLM_API_PORT_SGLANG"], "llm_slot")
    cap_existing = str(m.get("NVIDIA_DRIVER_CAPABILITIES", "")).strip()
    if not cap_existing:
        m["NVIDIA_DRIVER_CAPABILITIES"] = "compute,utility"
    return {k: str(v) for k, v in m.items() if v is not None and str(v) != ""}
