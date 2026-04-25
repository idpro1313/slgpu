"""Monitoring stack control."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import actor_from_header
from app.core.config import get_settings
from app.schemas.common import JobAccepted
from app.schemas.monitoring import ServiceOut, StackActionRequest
from app.services import jobs as jobs_service
from app.services.monitoring import probe_all
from app.services.slgpu_cli import cmd_monitoring

router = APIRouter()

_ALLOWED_ACTIONS = {"up", "down", "restart", "fix-perms"}


@router.get("/services", response_model=list[ServiceOut])
async def services() -> list[ServiceOut]:
    probes = await probe_all()
    return [
        ServiceOut(
            key=probe.probe.key,
            display_name=probe.probe.display_name,
            category=probe.probe.category,
            status=probe.status,
            container_id=probe.container.id if probe.container else None,
            url=probe.probe.web_url,
            detail=probe.detail,
            extra={
                "container_status": probe.container.status if probe.container else None,
                "image": probe.container.image if probe.container else None,
                "started_at": probe.container.started_at.isoformat() if probe.container and probe.container.started_at else None,
            },
            last_seen_at=None,
        )
        for probe in probes
    ]


@router.post("/action", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def stack_action(
    payload: StackActionRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    if payload.action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {sorted(_ALLOWED_ACTIONS)}")
    settings = get_settings()
    try:
        command = cmd_monitoring(settings.slgpu_root, payload.action)
    except ValueError as exc:
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
