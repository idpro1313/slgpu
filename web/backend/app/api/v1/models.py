"""HF model registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.security import ValidationError
from app.models.model import HFModel
from app.models.preset import Preset
from app.schemas.common import JobAccepted
from app.models.job import Job
from app.schemas.models import (
    HFModelCreate,
    HFModelOut,
    HFModelPullRequest,
    HFModelUpdate,
    ModelPullProgress,
    ModelSyncResult,
)
from app.core.config import get_settings
from app.services import hf_models as hf_service
from app.services import jobs as jobs_service
from app.services.slgpu_cli import cmd_pull
from app.services.ui_audit import record_ui_action

router = APIRouter()


def _pull_progress_from_job(job: Job | None) -> ModelPullProgress | None:
    if job is None:
        return None
    return ModelPullProgress(
        job_id=job.id,
        status=job.status.value,
        progress=job.progress,
        message=job.message,
    )


def _hf_model_out(item: HFModel, active_pull: Job | None) -> HFModelOut:
    base = HFModelOut.model_validate(item)
    return base.model_copy(update={"pull_progress": _pull_progress_from_job(active_pull)})


@router.get("", response_model=list[HFModelOut])
async def list_models(session: AsyncSession = Depends(db_session)) -> list[HFModelOut]:
    await hf_service.sync_local_models(session)
    await session.flush()
    result = await session.execute(select(HFModel).order_by(HFModel.hf_id))
    items = list(result.scalars().all())
    for item in items:
        await hf_service.refresh_status(session, item)
    active = await hf_service.active_pull_jobs_by_resource(session)
    return [_hf_model_out(m, active.get(m.hf_id)) for m in items]


@router.post("", response_model=HFModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: HFModelCreate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> HFModel:
    try:
        model = await hf_service.upsert_from_hf_id(
            session,
            payload.hf_id,
            revision=payload.revision,
            notes=payload.notes,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.flush()
    await record_ui_action(
        session,
        action="model.create",
        actor=actor,
        target=model.hf_id,
        note="registry create",
        payload={"hf_id": model.hf_id, "id": model.id},
    )
    return model


@router.post("/sync", response_model=ModelSyncResult)
async def sync_models_from_disk(
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> ModelSyncResult:
    """Подмешать папки в MODELS_DIR в реестр и обновить размер/статус у всех записей."""

    discovered = await hf_service.sync_local_models(session)
    result = await session.execute(select(HFModel).order_by(HFModel.hf_id))
    items = list(result.scalars().all())
    for item in items:
        await hf_service.refresh_status(session, item)
    await record_ui_action(
        session,
        action="models.sync",
        actor=actor,
        target=None,
        note=f"touched={len(discovered)} total={len(items)}",
        payload={"touched": len(discovered), "total": len(items)},
    )
    return ModelSyncResult(touched=len(discovered), total=len(items))


@router.get("/{model_id}", response_model=HFModelOut)
async def get_model(model_id: int, session: AsyncSession = Depends(db_session)) -> HFModelOut:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    await hf_service.refresh_status(session, model)
    active = await hf_service.active_pull_jobs_by_resource(session)
    return _hf_model_out(model, active.get(model.hf_id))


@router.patch("/{model_id}", response_model=HFModelOut)
async def update_model(
    model_id: int,
    payload: HFModelUpdate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> HFModel:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    if payload.revision is not None:
        model.revision = payload.revision
    if payload.notes is not None:
        model.notes = payload.notes
    await record_ui_action(
        session,
        action="model.update",
        actor=actor,
        target=model.hf_id,
        note="revision/notes",
        payload={"model_id": model_id, "hf_id": model.hf_id},
    )
    return model


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    delete_files: bool = Query(default=False),
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> dict[str, object]:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    hf = model.hf_id
    deleted_path = None
    if delete_files:
        try:
            deleted = hf_service.delete_local_model_files(model.hf_id)
        except (OSError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"delete files failed: {exc}") from exc
        deleted_path = str(deleted) if deleted is not None else None
    presets = await session.execute(select(Preset).where(Preset.model_id == model.id))
    for preset in presets.scalars().all():
        preset.model_id = None
    await record_ui_action(
        session,
        action="model.delete",
        actor=actor,
        target=hf,
        note=f"delete_files={delete_files}",
        payload={"model_id": model_id, "hf_id": hf, "delete_files": delete_files},
    )
    await session.delete(model)
    return {"deleted": True, "deleted_files": delete_files, "deleted_path": deleted_path}


@router.post("/{model_id}/pull", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def pull_model(
    model_id: int,
    payload: HFModelPullRequest,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")

    settings = get_settings()
    revision = payload.revision or model.revision
    try:
        command = cmd_pull(settings.slgpu_root, model.hf_id, revision=revision)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hf_service.mark_pull_started(session, model)
    await session.commit()

    try:
        job = await jobs_service.submit(
            command,
            actor=actor,
            extra_args={
                "model_id": model_id,
                "revision": revision,
                "hf_id": model.hf_id,
            },
        )
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )
