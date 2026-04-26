"""LiteLLM proxy status and helpers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.services.stack_config import ports_for_probes_sync
from app.services import app_settings
from app.services import litellm as litellm_service

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    return await litellm_service.health()


@router.get("/models")
async def list_models() -> list[dict[str, Any]]:
    return await litellm_service.list_models()


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
