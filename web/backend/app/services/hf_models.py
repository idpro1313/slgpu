"""Tracking and orchestration of HF model state."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stack_config import models_dir_sync
from app.core.security import ValidationError, validate_hf_id, validate_revision
from app.models.job import Job, JobStatus
from app.models.model import HFModel, ModelDownloadStatus
from app.services.env_files import hf_id_to_slug

logger = logging.getLogger(__name__)

_NATIVE_PULL_KIND = "native.model.pull"

_SAFETENSORS = ".safetensors"
_GGUF = ".gguf"
_BIN = ".bin"
_CONFIG = "config.json"


def _models_root() -> Path:
    """Weights directory from ``stack_params`` / merged stack in SQLite (``models_dir_sync``)."""

    try:
        return models_dir_sync()
    except Exception:  # noqa: BLE001
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


def delete_local_model_files(hf_id: str) -> Path | None:
    """Delete the model directory under MODELS_DIR, refusing paths outside it."""

    validate_hf_id(hf_id)
    root = _models_root().resolve()
    target = (root / hf_id).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValidationError("model path is outside MODELS_DIR") from exc
    if not target.exists():
        return None
    if not target.is_dir():
        raise ValidationError("model path is not a directory")
    shutil.rmtree(target)
    logger.info("[hf_models][delete_local_model_files] deleted=%s", target)
    return target


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


async def active_pull_jobs_by_resource(session: AsyncSession) -> dict[str, Job]:
    """Последняя активная задача pull по каждому `Job.resource` (HF id или slug, как в реестре)."""

    result = await session.execute(
        select(Job)
        .where(
            Job.kind == _NATIVE_PULL_KIND,
            Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
        )
        .order_by(Job.id.asc())
    )
    by_resource: dict[str, Job] = {}
    for job in result.scalars().all():
        if job.resource:
            by_resource[job.resource] = job
    return by_resource


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
