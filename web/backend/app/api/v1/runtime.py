"""Engine runtime endpoints (vLLM/SGLang)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import actor_from_header
from app.core.config import get_settings
from app.core.security import ValidationError
from app.schemas.common import JobAccepted
from app.schemas.runtime import (
    EngineDownRequest,
    EngineRestartRequest,
    EngineUpRequest,
    RuntimeSnapshot,
)
from app.services import jobs as jobs_service
from app.services import runtime as runtime_service
from app.services.slgpu_cli import cmd_down, cmd_restart, cmd_up

router = APIRouter()


@router.get("/snapshot", response_model=RuntimeSnapshot)
async def get_snapshot() -> RuntimeSnapshot:
    snap = await runtime_service.snapshot()
    return RuntimeSnapshot(
        engine=snap.engine,
        api_port=snap.api_port,
        container_status=snap.container_status,
        served_models=snap.served_models,
        metrics_available=snap.metrics_available,
        last_checked_at=snap.last_checked_at,
    )


@router.post("/up", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def runtime_up(
    payload: EngineUpRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    settings = get_settings()
    try:
        command = cmd_up(
            settings.slgpu_root,
            engine=payload.engine,
            preset=payload.preset,
            port=payload.port,
            tp=payload.tp,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        job = await jobs_service.submit(
            command,
            actor=actor,
            extra_args=payload.model_dump(),
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


@router.post("/down", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def runtime_down(
    payload: EngineDownRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    settings = get_settings()
    command = cmd_down(settings.slgpu_root, include_monitoring=payload.include_monitoring)
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args=payload.model_dump())
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )


@router.post("/restart", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def runtime_restart(
    payload: EngineRestartRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    settings = get_settings()
    try:
        command = cmd_restart(settings.slgpu_root, preset=payload.preset, tp=payload.tp)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args=payload.model_dump())
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )
