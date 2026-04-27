"""Merge stack + preset into env for vLLM/SGLang (compose or docker run)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.env_key_aliases import apply_vllm_aliases_to_merged, coalesce_str
from app.services.stack_config import parse_dotenv_text, presets_dir_sync, sync_merged_flat


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
    presets_dir = presets_dir_sync()
    pf = presets_dir / f"{preset}.env"
    if pf.is_file():
        m.update(parse_dotenv_text(pf.read_text(encoding="utf-8")))
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
            try:
                tpi = int(m.get("TP", "8"))
            except ValueError:
                tpi = 8
            m["NVIDIA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(max(1, tpi)))
    if port is not None:
        m["LLM_API_PORT"] = str(port)
    elif engine == "sglang" and "LLM_API_PORT" not in m:
        m["LLM_API_PORT"] = m.get("LLM_API_PORT_SGLANG", "8222")
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
        m["VLLM_PORT"] = coalesce_str(m, "VLLM_PORT", "SLGPU_VLLM_PORT", "LLM_API_PORT", default="8111")
    else:
        m["SGLANG_LISTEN_PORT"] = m.get("SGLANG_LISTEN_PORT", m.get("SGLANG_LISTEN", "8222"))
    return {k: str(v) for k, v in m.items() if v is not None and str(v) != ""}
