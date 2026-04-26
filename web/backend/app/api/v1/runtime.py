"""Engine runtime endpoints (vLLM/SGLang)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.config import get_settings
from app.core.security import (
    ValidationError,
    validate_engine,
    validate_port,
    validate_slot_key,
    validate_slug,
    validate_tp,
)
from app.models.preset import Preset
from app.models.run import EngineRun, RunStatus
from app.models.slot import EngineSlot
from app.schemas.common import JobAccepted
from app.schemas.runtime import (
    EngineDownRequest,
    EngineRestartRequest,
    EngineUpRequest,
    RuntimeLogs,
    RuntimeSlotView,
    RuntimeSnapshot,
)
from app.schemas.slot import EngineSlotOut, SlotCreateRequest, SlotRestartRequest
from app.services import gpu_availability
from app.services import jobs as jobs_service
from app.services import runtime as runtime_service
from app.services.slgpu_cli import (
    cmd_down,
    cmd_restart,
    cmd_slot_down,
    cmd_slot_restart,
    cmd_slot_up,
    cmd_up,
)

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
        slots=[
            RuntimeSlotView(
                slot_key=s.slot_key,
                engine=s.engine,
                preset_name=s.preset_name,
                hf_id=s.hf_id,
                api_port=s.api_port,
                tp=s.tp,
                gpu_indices=s.gpu_indices,
                container_status=s.container_status,
                container_name=s.container_name,
                served_models=s.served_models,
                metrics_available=s.metrics_available,
            )
            for s in snap.slots
        ],
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


@router.get("/slots", response_model=list[EngineSlotOut])
async def list_engine_slots(
    session: AsyncSession = Depends(db_session),
) -> list[EngineSlotOut]:
    res = await session.execute(select(EngineSlot).order_by(EngineSlot.slot_key))
    return list(res.scalars().all())


@router.get("/slots/{slot_key}/logs", response_model=RuntimeLogs)
async def get_slot_logs(
    slot_key: str, tail: int = Query(default=300, ge=1, le=2000)
) -> RuntimeLogs:
    try:
        validate_slot_key(slot_key)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logs = await runtime_service.tail_slot_logs(slot_key=slot_key, tail=tail)
    return RuntimeLogs(
        engine=logs.engine,
        container_name=logs.container_name,
        container_status=logs.container_status,
        tail=logs.tail,
        logs=logs.logs,
        last_checked_at=logs.last_checked_at,
    )


@router.post("/slots", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_engine_slot(
    payload: SlotCreateRequest,
    actor: str | None = Depends(actor_from_header),
    session: AsyncSession = Depends(db_session),
) -> JobAccepted:
    settings = get_settings()
    try:
        engine = validate_engine(payload.engine)
        preset_name = validate_slug(payload.preset)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    p = await _find_preset(session, preset_name)
    if p is None:
        raise HTTPException(status_code=404, detail="preset not found")
    tpi = payload.tp
    if tpi is None and p.tp is not None:
        tpi = int(p.tp)
    if tpi is None:
        tpi = 8
    validate_tp(tpi)
    gidx = list(payload.gpu_indices) if payload.gpu_indices else None
    if gidx is None or len(gidx) == 0:
        data = await gpu_availability.compute_availability(tp=tpi, exclude_slot_key=None)
        gidx = data.get("suggested")
        if not gidx and data.get("note") == "no_gpus_in_host_info":
            raise HTTPException(
                status_code=400, detail="No GPUs detected on host; set gpu_indices in request.",
            )
        if not gidx:
            raise HTTPException(
                status_code=409,
                detail="Not enough free GPUs; stop another slot or lower TP.",
            )
    if len(gidx) != tpi:
        raise HTTPException(
            status_code=400,
            detail=f"len(gpu_indices)={len(gidx)} does not match tp={tpi}",
        )
    sk = (payload.slot_key or "").strip() or f"s{uuid.uuid4().hex[:8]}"
    try:
        sk = validate_slot_key(sk)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dupe = await session.execute(select(EngineSlot).where(EngineSlot.slot_key == sk))
    if dupe.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="slot_key already in use")
    hport = payload.host_api_port
    if hport is None:
        hport = await _next_free_port(session, engine)
    else:
        try:
            validate_port(hport)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        command = cmd_slot_up(
            settings.slgpu_root,
            slot_key=sk,
            engine=engine,
            preset=preset_name,
            host_api_port=hport,
            gpu_indices=gidx,
            tp=tpi,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    jargs: dict = {
        "slot_key": sk,
        "engine": engine,
        "preset": preset_name,
        "host_api_port": hport,
        "gpu_indices": gidx,
        "tp": tpi,
    }
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args=jargs)
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )


@router.post("/slots/{slot_key}/down", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def slot_down(
    slot_key: str,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    settings = get_settings()
    try:
        validate_slot_key(slot_key)
        command = cmd_slot_down(settings.slgpu_root, slot_key=slot_key)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args={"slot_key": slot_key})
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
    )


@router.post("/slots/{slot_key}/restart", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def slot_restart(
    slot_key: str,
    payload: SlotRestartRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    settings = get_settings()
    try:
        validate_slot_key(slot_key)
        validate_slug(payload.preset)
        command = cmd_slot_restart(
            settings.slgpu_root,
            slot_key=slot_key,
            preset=payload.preset,
            host_api_port=payload.host_api_port,
            tp=payload.tp,
            gpu_indices=payload.gpu_indices,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ex = {
        "slot_key": slot_key,
        "preset": payload.preset,
        "host_api_port": payload.host_api_port,
        "tp": payload.tp,
        "gpu_indices": payload.gpu_indices,
    }
    try:
        job = await jobs_service.submit(command, actor=actor, extra_args=ex)
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=command.summary,
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


async def _next_free_port(session: AsyncSession, engine: str) -> int:
    res = await session.execute(select(EngineSlot.host_api_port).where(EngineSlot.host_api_port.isnot(None)))
    used = {int(p) for p in res.scalars().all() if p is not None}
    start, end = (8111, 8130) if engine == "vllm" else (8222, 8241)
    for p in range(start, end + 1):
        if p not in used:
            return p
    raise HTTPException(
        status_code=409, detail="no free host port in default range for this engine"
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
