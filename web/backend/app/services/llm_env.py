"""Merge stack + preset into env for vLLM/SGLang (compose or docker run)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.env_key_aliases import apply_vllm_aliases_to_merged, coalesce_str
from app.services.preset_db_sync import load_preset_flat_from_db_sync
from app.services.stack_config import sync_merged_flat
from app.services.stack_errors import MissingStackParams


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
    m.update(pextra)
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
        m["VLLM_PORT"] = coalesce_str(m, "VLLM_PORT", "SLGPU_VLLM_PORT", "LLM_API_PORT", default="")
        if not str(m["VLLM_PORT"]).strip():
            raise MissingStackParams(["VLLM_PORT", "LLM_API_PORT"], "llm_slot")
    else:
        m["SGLANG_LISTEN_PORT"] = coalesce_str(
            m, "SGLANG_LISTEN_PORT", "SGLANG_LISTEN", "LLM_API_PORT_SGLANG", default=""
        )
        if not str(m["SGLANG_LISTEN_PORT"]).strip():
            raise MissingStackParams(["SGLANG_LISTEN_PORT", "LLM_API_PORT_SGLANG"], "llm_slot")
    return {k: str(v) for k, v in m.items() if v is not None and str(v) != ""}
