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
from app.models.slot import EngineSlot, RunStatus
from app.schemas.common import JobAccepted
from app.schemas.runtime import (
    RuntimeLogs,
    RuntimeSlotView,
    RuntimeSnapshot,
)
from app.schemas.slot import EngineSlotOut, SlotCreateRequest, SlotRestartRequest
from app.services import gpu_availability
from app.services import jobs as jobs_service
from app.services import runtime as runtime_service
from app.services.stack_config import sync_merged_flat
from app.services.stack_registry import raise_if_missing
from app.services.slot_runtime import internal_api_port_for
from app.services.slgpu_cli import (
    cmd_slot_down,
    cmd_slot_restart,
    cmd_slot_up,
)

router = APIRouter()


@router.get("/snapshot", response_model=RuntimeSnapshot)
async def get_snapshot() -> RuntimeSnapshot:
    snap = await runtime_service.snapshot()
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
    stack_m = sync_merged_flat()
    raise_if_missing(stack_m, "port_allocation")
    # 8.0.0: модельные параметры — только из пресета. Валидируем их синхронно перед созданием job,
    # чтобы клиент получил понятный 409, а не «принято к выполнению» с фоновой ошибкой.
    from app.services.llm_env import PRESET_REQUIRED_KEYS
    from app.services.preset_db_sync import load_preset_flat_from_db_sync
    from app.services.stack_errors import MissingStackParams

    pextra_for_check = load_preset_flat_from_db_sync(preset_name) or {}
    missing_preset_fields = [
        k for k in PRESET_REQUIRED_KEYS if not str(pextra_for_check.get(k, "")).strip()
    ]
    if missing_preset_fields:
        raise MissingStackParams(
            [f"PRESET:{k}" for k in missing_preset_fields], "preset"
        )
    tpi = payload.tp
    if tpi is None and p.tp is not None:
        tpi = int(p.tp)
    if tpi is None:
        raise MissingStackParams([f"PRESET:{preset_name}:TP"], "preset")
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
    av = await gpu_availability.compute_availability(tp=tpi, exclude_slot_key=None)
    busy = {b["index"] for b in av.get("busy", []) if isinstance(b.get("index"), int)}
    overlap = set(gidx) & busy
    if overlap:
        raise HTTPException(
            status_code=409,
            detail=f"GPUs already in use: {sorted(overlap)}",
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
        hport = await _next_free_port(session, engine, stack_m)
    else:
        try:
            validate_port(hport)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    int_port = internal_api_port_for(engine, stack_m)
    now = datetime.now(timezone.utc)
    session.add(
        EngineSlot(
            slot_key=sk,
            engine=engine,
            preset_name=preset_name,
            hf_id=p.hf_id,
            tp=tpi,
            gpu_indices=",".join(str(i) for i in gidx),
            host_api_port=hport,
            internal_api_port=int_port,
            desired_status=RunStatus.RUNNING,
            observed_status=RunStatus.REQUESTED,
            started_at=now,
        )
    )
    await session.flush()
    # Commit before background job: native.slot.up reads EngineSlot in a new session.
    await session.commit()
    try:
        command = cmd_slot_up(
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
    force: bool = Query(
        default=False,
        description="Сразу остановить контейнеры слота, отменить job в БД, снять lock (долгий pull/up).",
    ),
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    try:
        validate_slot_key(slot_key)
        command = cmd_slot_down(slot_key=slot_key)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if force:
        cancelled = await jobs_service.force_engine_slot_halt(slot_key)
        return JobAccepted(
            job_id=0,
            correlation_id="00000000-0000-0000-0000-000000000000",
            kind=command.kind,
            status="forced",
            message="Принудительная остановка: контейнеры слота, отмена задач, lock снят.",
            forced=True,
            cancelled_job_ids=cancelled,
        )
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
    try:
        validate_slot_key(slot_key)
        validate_slug(payload.preset)
        command = cmd_slot_restart(
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


async def _next_free_port(
    session: AsyncSession, engine: str, stack_m: dict[str, str]
) -> int:
    res = await session.execute(
        select(EngineSlot.host_api_port).where(EngineSlot.host_api_port.isnot(None))
    )
    used = {int(p) for p in res.scalars().all() if p is not None}
    if engine == "vllm":
        start = int(stack_m["LLM_HOST_PORT_RANGE_VLLM_START"])
        end = int(stack_m["LLM_HOST_PORT_RANGE_VLLM_END"])
    else:
        start = int(stack_m["LLM_HOST_PORT_RANGE_SGLANG_START"])
        end = int(stack_m["LLM_HOST_PORT_RANGE_SGLANG_END"])
    for p in range(start, end + 1):
        if p not in used:
            return p
    raise HTTPException(
        status_code=409, detail="no free host port in default range for this engine"
    )


async def _find_preset(session: AsyncSession, name: str) -> Preset | None:
    result = await session.execute(select(Preset).where(Preset.name == name))
    return result.scalar_one_or_none()
