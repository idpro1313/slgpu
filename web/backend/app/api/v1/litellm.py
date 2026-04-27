"""LiteLLM proxy status and helpers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.config import get_settings
from app.schemas.common import JobAccepted
from app.schemas.monitoring import StackActionRequest
from app.services.stack_config import ports_for_probes_sync, sync_merged_flat
from app.services.stack_registry import raise_if_missing
from app.services import app_settings
from app.services import jobs as jobs_service
from app.services import litellm as litellm_service
from app.services.slgpu_cli import cmd_proxy

router = APIRouter()

_PROXY_ACTIONS = frozenset({"up", "down", "restart"})


@router.get("/health")
async def health(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    return await litellm_service.health(session)


@router.get("/models")
async def list_models(session: AsyncSession = Depends(db_session)) -> list[dict[str, Any]]:
    return await litellm_service.list_models(session)


@router.get("/info")
async def info(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    urls = await app_settings.get_public_urls(session, request)
    return {
        "ui_url": urls["litellm"],
        "api_url": urls["litellm_api"],
        "port": int(ports_for_probes_sync()["litellm_port"]),
        "note": "Routes and pricing are configured in LiteLLM Admin UI / DB.",
    }


@router.post("/proxy/action", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def proxy_stack_action(
    payload: StackActionRequest,
    actor: str | None = Depends(actor_from_header),
) -> JobAccepted:
    """Старт/стоп/перезапуск только `docker-compose.proxy.yml` (проект LiteLLM). Lock совпадает с полным `monitoring` (scope `monitoring` / `stack`)."""
    if payload.action not in _PROXY_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(_PROXY_ACTIONS)}",
        )
    merged = sync_merged_flat()
    raise_if_missing(merged, "proxy_up")
    settings = get_settings()
    try:
        command = cmd_proxy(settings.slgpu_root, payload.action)
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
