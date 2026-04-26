"""Read-only adapter for the LiteLLM Admin API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import app_settings
from app.services.stack_config import ports_for_probes_sync

logger = logging.getLogger(__name__)


async def _bearer_headers(session: AsyncSession | None) -> dict[str, str]:
    if session is None:
        return {}
    key = await app_settings.get_litellm_api_key(session)
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


async def list_models(session: AsyncSession | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    h = settings.monitoring_http_host
    port = int(ports_for_probes_sync()["litellm_port"])
    url = f"http://{h}:{port}/v1/models"
    headers = await _bearer_headers(session)
    async with httpx.AsyncClient(timeout=3.0, headers=headers) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return []
            return response.json().get("data", [])
        except httpx.HTTPError as exc:
            logger.warning("[litellm][list_models] %s", exc)
            return []


async def health(session: AsyncSession | None = None) -> dict[str, Any]:
    settings = get_settings()
    h = settings.monitoring_http_host
    port = int(ports_for_probes_sync()["litellm_port"])
    base = f"http://{h}:{port}"
    out: dict[str, Any] = {"liveliness": False, "readiness": False, "ui": False}
    headers = await _bearer_headers(session)
    async with httpx.AsyncClient(timeout=2.0, headers=headers) as client:
        for key, path in (("liveliness", "/health/liveliness"), ("readiness", "/health/readiness")):
            try:
                response = await client.get(f"{base}{path}")
                out[key] = 200 <= response.status_code < 400
            except httpx.HTTPError:
                out[key] = False
        try:
            response = await client.get(f"{base}/ui", headers=headers)
            out["ui"] = 200 <= response.status_code < 400
        except httpx.HTTPError:
            out["ui"] = False
    return out
