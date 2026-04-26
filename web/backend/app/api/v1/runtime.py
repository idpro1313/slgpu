"""Engine runtime endpoints (vLLM/SGLang)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.config import get_settings
from app.core.security import ValidationError
from app.models.preset import Preset
from app.models.run import EngineRun, RunStatus
from app.schemas.common import JobAccepted
from app.schemas.runtime import (
    EngineDownRequest,
    EngineRestartRequest,
    EngineUpRequest,
    RuntimeLogs,
    RuntimeSnapshot,
)
from app.services import jobs as jobs_service
from app.services import runtime as runtime_service
from app.services.slgpu_cli import cmd_down, cmd_restart, cmd_up

router = APIRouter()


@router.get("/snapshot", response_model=RuntimeSnapshot)
async def get_snapshot(session: AsyncSession = Depends(db_session)) -> RuntimeSnapshot:
    snap = await runtime_service.snapshot()
    await runtime_service.attach_run_metadata(session, snap)
    return RuntimeSnapshot(
        engine=snap.engine,
        api_port=snap.api_port,
        container_status=snap.container_status,
        preset_name=snap.preset_name,
        hf_id=snap.hf_id,
        tp=snap.tp,
        served_models=snap.served_models,
        metrics_available=snap.metrics_available,
        last_checked_at=snap.last_checked_at,
    )


@router.get("/logs", response_model=RuntimeLogs)
async def get_logs(tail: int = Query(default=300, ge=1, le=2000)) -> RuntimeLogs:
    logs = runtime_service.tail_container_logs(tail=tail)
    return RuntimeLogs(
        engine=logs.engine,
        container_name=logs.container_name,
        container_status=logs.container_status,
        tail=logs.tail,
        logs=logs.logs,
        last_checked_at=logs.last_checked_at,
    )


@router.post("/up", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def runtime_up(
    payload: EngineUpRequest,
    actor: str | None = Depends(actor_from_header),
    session: AsyncSession = Depends(db_session),
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

    preset = await _find_preset(session, payload.preset)
    session.add(
        EngineRun(
            engine=payload.engine,
            preset_name=payload.preset,
            api_port=payload.port,
            tp=payload.tp if payload.tp is not None else (preset.tp if preset else None),
            gpu_mask=preset.gpu_mask if preset else None,
            desired_status=RunStatus.RUNNING,
            observed_status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            extra={"hf_id": preset.hf_id} if preset else {},
        )
    )

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
    session: AsyncSession = Depends(db_session),
) -> JobAccepted:
    settings = get_settings()
    command = cmd_down(settings.slgpu_root, include_monitoring=payload.include_monitoring)
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args=payload.model_dump())
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    result = await session.execute(
        select(EngineRun).where(EngineRun.observed_status != RunStatus.STOPPED)
    )
    now = datetime.now(timezone.utc)
    for run in result.scalars().all():
        run.desired_status = RunStatus.STOPPED
        run.observed_status = RunStatus.STOPPED
        run.stopped_at = now
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
    session: AsyncSession = Depends(db_session),
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
    snap = await runtime_service.snapshot()
    latest = await _latest_active_run(session)
    preset = await _find_preset(session, payload.preset)
    engine = snap.engine or (latest.engine if latest else "vllm")
    session.add(
        EngineRun(
            engine=engine,
            preset_name=payload.preset,
            api_port=snap.api_port or (latest.api_port if latest else None),
            tp=payload.tp if payload.tp is not None else (preset.tp if preset else None),
            gpu_mask=preset.gpu_mask if preset else None,
            desired_status=RunStatus.RUNNING,
            observed_status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            extra={"hf_id": preset.hf_id} if preset else {},
        )
    )
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )


async def _find_preset(session: AsyncSession, name: str) -> Preset | None:
    result = await session.execute(select(Preset).where(Preset.name == name))
    return result.scalar_one_or_none()


async def _latest_active_run(session: AsyncSession) -> EngineRun | None:
    result = await session.execute(
        select(EngineRun)
        .where(EngineRun.observed_status != RunStatus.STOPPED)
        .order_by(EngineRun.updated_at.desc(), EngineRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
