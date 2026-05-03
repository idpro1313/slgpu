"""Bridge between DB presets and the slgpu `data/presets/*.env` files (PRESETS_DIR)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ValidationError, validate_hf_id, validate_slug, validate_tp
from app.models.model import HFModel, ModelDownloadStatus
from app.models.preset import Preset
from app.services.env_key_aliases import LEGACY_VLLM_PARAM_KEYS, apply_vllm_aliases_to_merged
from app.services.env_files import (
    EnvFile,
    hf_id_to_slug,
    list_preset_files,
    parse_env_file,
    parse_env_text,
    write_preset_file,
)

logger = logging.getLogger(__name__)


class PresetImportConflict(Exception):
    """Имя пресета уже занято в БД при импорте без overwrite."""

    name: str

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


# Канонические ключи vLLM/SGLang в parameters / экспорт; устаревшие SLGPU_* принимаем при импорте.
# 8.1.3: `TP`, `MODEL_ID`, `SERVED_MODEL_NAME` НЕ входят в parameters — у них выделенные колонки в БД
# (`presets.tp` / `presets.hf_id` / `presets.served_model_name`), они редактируются ТОЛЬКО в шапке
# карточки UI. Дублирование вело к расхождению `TP` шапки и `TP` в parameters (см. 8.1.2-troubleshooting).
PRESET_HEADER_ONLY_KEYS: frozenset[str] = frozenset({"TP", "MODEL_ID", "SERVED_MODEL_NAME"})

_RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        "MAX_MODEL_LEN",
        "KV_CACHE_DTYPE",
        "GPU_MEM_UTIL",
        "VLLM_DOCKER_IMAGE",
        "MODEL_REVISION",
        "MAX_NUM_BATCHED_TOKENS",
        "MAX_NUM_SEQS",
        "BLOCK_SIZE",
        "DISABLE_CUSTOM_ALL_REDUCE",
        "ENABLE_PREFIX_CACHING",
        "ENABLE_EXPERT_PARALLEL",
        "ENABLE_CHUNKED_PREFILL",
        "ENABLE_AUTO_TOOL_CHOICE",
        "TRUST_REMOTE_CODE",
        "DATA_PARALLEL_SIZE",
        "ATTENTION_BACKEND",
        "TOKENIZER_MODE",
        "COMPILATION_CONFIG",
        "ENFORCE_EAGER",
        "SPECULATIVE_CONFIG",
        "MM_ENCODER_TP_MODE",
        "TOOL_CALL_PARSER",
        "REASONING_PARSER",
        "CHAT_TEMPLATE_CONTENT_FORMAT",
        "TORCH_FLOAT32_MATMUL_PRECISION",
        "VLLM_USE_V1",
        "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS",
        "SGLANG_MEM_FRACTION_STATIC",
        "SGLANG_CUDA_GRAPH_MAX_BS",
        "SGLANG_ENABLE_TORCH_COMPILE",
        "SGLANG_DISABLE_CUDA_GRAPH",
        "SGLANG_DISABLE_CUSTOM_ALL_REDUCE",
        "BENCH_MODEL_NAME",
    }
)


def _normalize_preset_param_dict(raw: dict[str, str]) -> dict[str, str]:
    m = {k: v for k, v in raw.items() if v not in (None, "")}
    apply_vllm_aliases_to_merged(m)
    return {k: m[k] for k in _RUNTIME_KEYS if k in m and str(m[k]).strip() != ""}


def presentation_preset_parameters(params: Any) -> dict[str, str]:
    """Канонические ключи `parameters` для API, БД и export (без SLGPU_*-алиасов)."""
    if not params or not isinstance(params, dict):
        return {}
    raw = {str(k): str(v) for k, v in params.items() if v is not None and str(v).strip() != ""}
    raw_p = {k: v for k, v in raw.items() if k in _RUNTIME_KEYS or k in LEGACY_VLLM_PARAM_KEYS}
    return _normalize_preset_param_dict(raw_p)


async def migrate_preset_parameters_to_canonical_if_needed(session: AsyncSession) -> None:
    """Переписать устаревшие ключи в `presets.parameters`.

    Срабатывает на:
    - SLGPU_* из импорта <4.2 (`LEGACY_VLLM_PARAM_KEYS`);
    - 8.1.3: `TP`/`MODEL_ID`/`SERVED_MODEL_NAME` в parameters — они зеркалят выделенные колонки
      БД и приводят к расхождению (`TP=8` в parameters при `presets.tp=2` в шапке). Извлекаем
      в столбец, если он не задан, и удаляем из parameters.
    """

    r = await session.execute(select(Preset))
    n = 0
    for preset in r.scalars().all():
        old = preset.parameters
        if not old or not isinstance(old, dict):
            continue
        has_legacy = any(k in old for k in LEGACY_VLLM_PARAM_KEYS)
        has_header_dup = any(k in old for k in PRESET_HEADER_ONLY_KEYS)
        if not has_legacy and not has_header_dup:
            continue
        if has_header_dup:
            tp_param = old.get("TP")
            if tp_param is not None and str(tp_param).strip() and preset.tp is None:
                try:
                    preset.tp = int(str(tp_param).strip())
                except ValueError:
                    pass
            sn_param = old.get("SERVED_MODEL_NAME")
            if sn_param and not preset.served_model_name:
                preset.served_model_name = str(sn_param).strip() or None
            mid_param = old.get("MODEL_ID")
            if mid_param and not preset.hf_id:
                preset.hf_id = str(mid_param).strip()
        preset.parameters = presentation_preset_parameters(old)
        n += 1
    if n:
        logger.info(
            "[presets][migrate_preset_parameters][BLOCK_MIGRATED] presets_updated=%s",
            n,
        )


def presets_dir() -> Path:
    return get_settings().models_presets_dir


def copy_example_presets_to_disk() -> tuple[int, int, list[str]]:
    """Скопировать ``*.env`` из ``examples/presets`` в PRESETS_DIR.

    Существующие файлы с тем же именем не перезаписываются (пропуск).

    Returns:
        (copied, skipped_existing, errors)
    """

    settings = get_settings()
    root = settings.slgpu_root.resolve()
    src_root = (root / "examples" / "presets").resolve()
    try:
        src_root.relative_to(root)
    except ValueError:
        return 0, 0, ["examples/presets is outside SLGPU_ROOT"]

    if not src_root.is_dir():
        return 0, 0, [f"missing examples presets directory: {src_root}"]

    dest_root = presets_dir().resolve()
    copied = 0
    skipped = 0
    errors: list[str] = []

    for path in list_preset_files(src_root):
        slug = path.stem
        try:
            validate_slug(slug)
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        dest = dest_root / f"{slug}.env"
        if dest.exists():
            skipped += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied += 1
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")

    return copied, skipped, errors


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
        raw_p = {k: v for k, v in env.values.items() if k in _RUNTIME_KEYS or k in LEGACY_VLLM_PARAM_KEYS}
        params = _normalize_preset_param_dict(raw_p)

        if preset is None:
            preset = Preset(
                name=env.slug,
                description=f"Imported from {path.name}",
                hf_id=env.hf_id,
                tp=_int_or_none(env.values.get("TP")),
                served_model_name=env.values.get("SERVED_MODEL_NAME")
                or env.values.get("SLGPU_SERVED_MODEL_NAME"),
                parameters=params,
                file_path=str(path),
                is_synced=True,
                is_active=True,
            )
            session.add(preset)
            imported += 1
        else:
            preset.hf_id = env.hf_id
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


async def import_presets_from_disk(
    session: AsyncSession,
    directory: Path,
) -> tuple[int, int, int, list[str]]:
    """Одноразовый seed пресетов из ``data/presets/*.env`` при install (алиас для тестов и app_config)."""

    return await import_files_into_db(session, directory)


async def export_preset_to_file(session: AsyncSession, preset: Preset) -> Path:
    settings = get_settings()
    validate_slug(preset.name)
    values: dict[str, str] = {}
    values["MODEL_ID"] = preset.hf_id
    if preset.served_model_name:
        values["SERVED_MODEL_NAME"] = preset.served_model_name
    if preset.tp is not None:
        values["TP"] = str(preset.tp)
    for key, raw in presentation_preset_parameters(preset.parameters).items():
        values[key] = raw

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
        "tp": _int_or_none(env.values.get("TP")),
        "served_model_name": env.values.get("SERVED_MODEL_NAME")
        or env.values.get("SLGPU_SERVED_MODEL_NAME"),
        "parameters": _normalize_preset_param_dict(
            {k: v for k, v in env.values.items() if k in _RUNTIME_KEYS or k in LEGACY_VLLM_PARAM_KEYS}
        ),
    }


async def import_preset_from_env_text(
    session: AsyncSession,
    *,
    name: str,
    text: str,
    overwrite: bool,
    source_filename: str | None = None,
) -> Preset:
    """Разбор текста пресета (`.env`) и создание или обновление строки ``presets``.

    Имя пресета — ``name`` (slug). При ``overwrite=False`` и существующей записи —
    ``PresetImportConflict``.
    """

    validate_slug(name)
    values = parse_env_text(text)
    hf_raw = values.get("MODEL_ID")
    if hf_raw is None or not str(hf_raw).strip():
        msg = "в файле нет MODEL_ID"
        raise ValueError(msg)
    hf_id = str(hf_raw).strip()
    try:
        validate_hf_id(hf_id)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    tp_val = _int_or_none(values.get("TP"))
    if tp_val is not None:
        try:
            validate_tp(tp_val)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    raw_param = {
        k: v
        for k, v in values.items()
        if k in _RUNTIME_KEYS or k in LEGACY_VLLM_PARAM_KEYS
    }
    params = presentation_preset_parameters(raw_param)

    served = values.get("SERVED_MODEL_NAME") or values.get("SLGPU_SERVED_MODEL_NAME")
    served_or = str(served).strip() if served else None

    q = await session.execute(select(Preset).where(Preset.name == name))
    preset = q.scalar_one_or_none()
    if preset is not None and not overwrite:
        raise PresetImportConflict(name)

    model_q = await session.execute(select(HFModel).where(HFModel.hf_id == hf_id))
    model = model_q.scalar_one_or_none()
    if model is None:
        model = HFModel(
            hf_id=hf_id,
            revision=values.get("MODEL_REVISION") or None,
            slug=hf_id_to_slug(hf_id),
            download_status=ModelDownloadStatus.UNKNOWN,
        )
        session.add(model)
    await session.flush()

    src = f" ({source_filename})" if source_filename else ""
    desc = f"Imported from uploaded file{src}"

    if preset is None:
        preset = Preset(
            name=name,
            description=desc,
            model_id=model.id,
            hf_id=hf_id,
            tp=tp_val,
            gpu_mask=None,
            served_model_name=served_or,
            parameters=params,
            file_path=None,
            is_synced=False,
            is_active=True,
        )
        session.add(preset)
    else:
        preset.hf_id = hf_id
        preset.model_id = model.id
        preset.tp = tp_val
        preset.served_model_name = served_or
        preset.parameters = params
        preset.file_path = None
        preset.is_synced = False
        preset.is_active = True

    await session.flush()
    return preset
