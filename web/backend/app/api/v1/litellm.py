"""LiteLLM proxy status and helpers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.services import litellm as litellm_service

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    return await litellm_service.health()


@router.get("/models")
async def list_models() -> list[dict[str, Any]]:
    return await litellm_service.list_models()


@router.get("/info")
async def info() -> dict[str, Any]:
    settings = get_settings()
    return {
        "ui_url": f"http://127.0.0.1:{settings.litellm_port}/ui",
        "api_url": f"http://127.0.0.1:{settings.litellm_port}/v1",
        "port": settings.litellm_port,
        "note": "Routes and pricing are configured in LiteLLM Admin UI / DB.",
    }
