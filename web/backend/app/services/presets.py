"""Bridge between DB presets and the slgpu `data/presets/*.env` files (PRESETS_DIR)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import validate_slug
from app.models.model import HFModel, ModelDownloadStatus
from app.models.preset import Preset
from app.services.env_files import (
    EnvFile,
    hf_id_to_slug,
    list_preset_files,
    parse_env_file,
    write_preset_file,
)

logger = logging.getLogger(__name__)


_RUNTIME_KEYS = {
    "MAX_MODEL_LEN",
    "TP",
    "KV_CACHE_DTYPE",
    "GPU_MEM_UTIL",
    "VLLM_DOCKER_IMAGE",
    "MODEL_REVISION",
    "SLGPU_MAX_NUM_BATCHED_TOKENS",
    "SLGPU_VLLM_MAX_NUM_SEQS",
    "SLGPU_VLLM_BLOCK_SIZE",
    "SLGPU_DISABLE_CUSTOM_ALL_REDUCE",
    "SLGPU_ENABLE_PREFIX_CACHING",
    "SLGPU_ENABLE_EXPERT_PARALLEL",
    "SLGPU_VLLM_DATA_PARALLEL_SIZE",
    "SLGPU_VLLM_ATTENTION_BACKEND",
    "SLGPU_VLLM_TOKENIZER_MODE",
    "SLGPU_VLLM_COMPILATION_CONFIG",
    "SLGPU_VLLM_ENFORCE_EAGER",
    "SLGPU_VLLM_SPECULATIVE_CONFIG",
    "MM_ENCODER_TP_MODE",
    "TOOL_CALL_PARSER",
    "REASONING_PARSER",
    "CHAT_TEMPLATE_CONTENT_FORMAT",
    "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS",
    "SGLANG_MEM_FRACTION_STATIC",
    "SGLANG_CUDA_GRAPH_MAX_BS",
    "SGLANG_ENABLE_TORCH_COMPILE",
    "SGLANG_DISABLE_CUDA_GRAPH",
    "SGLANG_DISABLE_CUSTOM_ALL_REDUCE",
    "BENCH_MODEL_NAME",
}


def presets_dir() -> Path:
    return get_settings().models_presets_dir


def _engine_from_values(values: dict[str, str]) -> str:
    """Infer vllm|sglang from .env. Prefer explicit SLGPU_ENGINE; else heuristic."""

    raw = (values.get("SLGPU_ENGINE") or "").strip().lower()
    if raw in ("vllm", "sglang"):
        return raw
    if "SGLANG_MEM_FRACTION_STATIC" in values:
        return "sglang"
    return "vllm"


async def import_files_into_db(
    session: AsyncSession,
    directory: Path | None = None,
) -> tuple[int, int, int, list[str]]:
    """Import all `*.env` from the presets directory into DB presets.

    Returns (imported, updated, skipped, errors).
    """

    settings = get_settings()
    directory = directory or settings.models_presets_dir
    imported = updated = skipped = 0
    errors: list[str] = []

    for path in list_preset_files(directory):
        try:
            env = parse_env_file(path)
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
            continue

        if not env.hf_id:
            skipped += 1
            errors.append(f"{path.name}: no MODEL_ID, skipped")
            continue

        existing = await session.execute(select(Preset).where(Preset.name == env.slug))
        preset = existing.scalar_one_or_none()
        params = {k: v for k, v in env.values.items() if k in _RUNTIME_KEYS}

        if preset is None:
            preset = Preset(
                name=env.slug,
                description=f"Imported from {path.name}",
                hf_id=env.hf_id,
                engine=_engine_from_values(env.values),
                tp=_int_or_none(env.values.get("TP")),
                served_model_name=env.values.get("SLGPU_SERVED_MODEL_NAME"),
                parameters=params,
                file_path=str(path),
                is_synced=True,
                is_active=True,
            )
            session.add(preset)
            imported += 1
        else:
            preset.hf_id = env.hf_id
            preset.engine = preset.engine or _engine_from_values(env.values)
            preset.parameters = params
            preset.file_path = str(path)
            preset.is_synced = True
            updated += 1

        model_q = await session.execute(select(HFModel).where(HFModel.hf_id == env.hf_id))
        model = model_q.scalar_one_or_none()
        if model is None:
            model = HFModel(
                hf_id=env.hf_id,
                revision=env.values.get("MODEL_REVISION") or None,
                slug=hf_id_to_slug(env.hf_id),
                download_status=ModelDownloadStatus.UNKNOWN,
            )
            session.add(model)
        await session.flush()
        preset.model_id = model.id

    return imported, updated, skipped, errors


async def export_preset_to_file(session: AsyncSession, preset: Preset) -> Path:
    settings = get_settings()
    validate_slug(preset.name)
    values: dict[str, str] = {}
    values["MODEL_ID"] = preset.hf_id
    values["SLGPU_ENGINE"] = preset.engine if preset.engine in ("vllm", "sglang") else "vllm"
    if preset.served_model_name:
        values["SLGPU_SERVED_MODEL_NAME"] = preset.served_model_name
    if preset.tp is not None:
        values["TP"] = str(preset.tp)
    for key, raw in (preset.parameters or {}).items():
        if raw is None or raw == "":
            continue
        values[str(key)] = str(raw)

    target = write_preset_file(
        settings.models_presets_dir,
        preset.name,
        values,
        header=(
            f"Generated by slgpu-web for preset '{preset.name}'.\n"
            f"Source of truth: web UI. Manual edits stay until next export."
        ),
    )
    preset.file_path = str(target)
    preset.is_synced = True
    return target


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def env_to_preset_dict(env: EnvFile) -> dict[str, Any]:
    """Helper for tests and ad-hoc previews."""

    return {
        "name": env.slug,
        "hf_id": env.hf_id,
        "engine": _engine_from_values(env.values),
        "tp": _int_or_none(env.values.get("TP")),
        "served_model_name": env.values.get("SLGPU_SERVED_MODEL_NAME"),
        "parameters": {k: v for k, v in env.values.items() if k in _RUNTIME_KEYS},
    }
