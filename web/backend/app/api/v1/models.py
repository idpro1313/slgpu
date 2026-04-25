"""HF model registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.security import ValidationError
from app.models.model import HFModel
from app.schemas.common import JobAccepted
from app.schemas.models import HFModelCreate, HFModelOut, HFModelPullRequest, HFModelUpdate
from app.services import hf_models as hf_service
from app.services import jobs as jobs_service
from app.services.slgpu_cli import cmd_pull
from app.core.config import get_settings

router = APIRouter()


@router.get("", response_model=list[HFModelOut])
async def list_models(session: AsyncSession = Depends(db_session)) -> list[HFModel]:
    result = await session.execute(select(HFModel).order_by(HFModel.hf_id))
    items = list(result.scalars().all())
    for item in items:
        await hf_service.refresh_status(session, item)
    return items


@router.post("", response_model=HFModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: HFModelCreate,
    session: AsyncSession = Depends(db_session),
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
    return model


@router.get("/{model_id}", response_model=HFModelOut)
async def get_model(model_id: int, session: AsyncSession = Depends(db_session)) -> HFModel:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    await hf_service.refresh_status(session, model)
    return model


@router.patch("/{model_id}", response_model=HFModelOut)
async def update_model(
    model_id: int,
    payload: HFModelUpdate,
    session: AsyncSession = Depends(db_session),
) -> HFModel:
    model = await session.get(HFModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    if payload.revision is not None:
        model.revision = payload.revision
    if payload.notes is not None:
        model.notes = payload.notes
    return model


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
            extra_args={"model_id": model_id, "revision": revision},
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
