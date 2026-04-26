"""Tracking and orchestration of HF model state."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ValidationError, validate_hf_id, validate_revision
from app.models.model import HFModel, ModelDownloadStatus
from app.services.env_files import hf_id_to_slug

logger = logging.getLogger(__name__)

_SAFETENSORS = ".safetensors"
_GGUF = ".gguf"
_BIN = ".bin"
_CONFIG = "config.json"


def _models_root() -> Path:
    """Resolve where slgpu CLI puts the weights.

    Reads `MODELS_DIR` from `main.env` if present, otherwise defaults
    to `/opt/models` to match the slgpu README.

    Relative paths (e.g. ``./data/models``) are resolved from ``slgpu_root``
    (``/slgpu`` in the web container), so they match the bind mount in
    ``docker/docker-compose.web.yml``.
    """

    settings = get_settings()
    main_env = settings.main_env_path
    root = settings.slgpu_root
    if main_env.exists():
        for line in main_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("MODELS_DIR=") and not stripped.startswith("#"):
                value = stripped.split("=", 1)[1].strip()
                if not value:
                    break
                if value.startswith("./"):
                    return (root / value[2:]).resolve()
                p = Path(value)
                if p.is_absolute():
                    return p
                return (root / value).resolve()
    return Path("/opt/models")


def _scan_local_state(hf_id: str) -> tuple[ModelDownloadStatus, int | None]:
    target = _models_root() / hf_id
    if not target.exists() or not target.is_dir():
        return ModelDownloadStatus.UNKNOWN, None

    has_config = (target / _CONFIG).exists()
    has_weights = False
    incomplete = False
    total_size = 0
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {_SAFETENSORS, _GGUF, _BIN}:
            has_weights = True
        if path.name.endswith(".incomplete") or path.name.endswith(".part"):
            incomplete = True
        try:
            total_size += path.stat().st_size
        except OSError:
            continue

    if incomplete:
        return ModelDownloadStatus.PARTIAL, total_size
    if has_config and has_weights:
        return ModelDownloadStatus.READY, total_size
    if total_size > 0:
        return ModelDownloadStatus.PARTIAL, total_size
    return ModelDownloadStatus.UNKNOWN, None


def _iter_local_hf_ids() -> list[str]:
    root = _models_root()
    if not root.exists() or not root.is_dir():
        return []

    hf_ids: list[str] = []
    for org_dir in sorted(root.iterdir()):
        if not org_dir.is_dir() or org_dir.name.startswith("."):
            continue
        for model_dir in sorted(org_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith("."):
                continue
            hf_id = f"{org_dir.name}/{model_dir.name}"
            try:
                validate_hf_id(hf_id)
            except ValidationError:
                logger.debug("[hf_models][_iter_local_hf_ids] skip invalid local path %s", hf_id)
                continue
            hf_ids.append(hf_id)
    return hf_ids


async def sync_local_models(session: AsyncSession) -> list[HFModel]:
    """Ensure DB registry includes actual folders from MODELS_DIR.

    Presets are launch recipes, not the source of truth for downloaded
    weights. The local model registry follows the disk layout produced by
    `./slgpu pull`: MODELS_DIR/<org>/<repo>.
    """

    models: list[HFModel] = []
    for hf_id in _iter_local_hf_ids():
        existing = await session.execute(select(HFModel).where(HFModel.hf_id == hf_id))
        model = existing.scalar_one_or_none()
        status, size = _scan_local_state(hf_id)
        target = _models_root() / hf_id
        if model is None:
            model = HFModel(
                hf_id=hf_id,
                slug=hf_id_to_slug(hf_id),
                local_path=str(target),
                size_bytes=size,
                download_status=status,
            )
            session.add(model)
        else:
            model.local_path = str(target)
            model.size_bytes = size
            model.download_status = status
        models.append(model)
    return models


async def upsert_from_hf_id(
    session: AsyncSession,
    hf_id: str,
    *,
    revision: str | None = None,
    notes: str | None = None,
) -> HFModel:
    validate_hf_id(hf_id)
    if revision:
        validate_revision(revision)

    existing = await session.execute(select(HFModel).where(HFModel.hf_id == hf_id))
    model = existing.scalar_one_or_none()

    status, size = _scan_local_state(hf_id)
    target = _models_root() / hf_id

    if model is None:
        model = HFModel(
            hf_id=hf_id,
            revision=revision,
            slug=hf_id_to_slug(hf_id),
            local_path=str(target) if target.exists() else None,
            size_bytes=size,
            download_status=status,
            notes=notes,
        )
        session.add(model)
    else:
        if revision is not None:
            model.revision = revision
        model.size_bytes = size
        model.download_status = status
        if target.exists():
            model.local_path = str(target)
        if notes is not None:
            model.notes = notes
    return model


async def refresh_status(session: AsyncSession, model: HFModel) -> HFModel:
    status, size = _scan_local_state(model.hf_id)
    model.download_status = status
    model.size_bytes = size
    target = _models_root() / model.hf_id
    if target.exists():
        model.local_path = str(target)
    return model


async def mark_pull_started(session: AsyncSession, model: HFModel) -> None:
    model.download_status = ModelDownloadStatus.DOWNLOADING
    model.attempts += 1
    model.last_error = None


async def mark_pull_finished(
    session: AsyncSession,
    model: HFModel,
    *,
    success: bool,
    error: str | None = None,
) -> None:
    if success:
        model.last_pulled_at = datetime.now(timezone.utc)
        await refresh_status(session, model)
    else:
        model.last_error = error
        model.download_status = ModelDownloadStatus.ERROR
