"""Read-only adapter for the LiteLLM Admin API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def list_models() -> list[dict[str, Any]]:
    settings = get_settings()
    h = settings.monitoring_http_host
    url = f"http://{h}:{settings.litellm_port}/v1/models"
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return []
            return response.json().get("data", [])
        except httpx.HTTPError as exc:
            logger.warning("[litellm][list_models] %s", exc)
            return []


async def health() -> dict[str, Any]:
    settings = get_settings()
    h = settings.monitoring_http_host
    base = f"http://{h}:{settings.litellm_port}"
    out: dict[str, Any] = {"liveliness": False, "readiness": False, "ui": False}
    async with httpx.AsyncClient(timeout=2.0) as client:
        for key, path in (("liveliness", "/health/liveliness"), ("readiness", "/health/readiness")):
            try:
                response = await client.get(f"{base}{path}")
                out[key] = 200 <= response.status_code < 400
            except httpx.HTTPError:
                out[key] = False
        try:
            response = await client.get(f"{base}/ui")
            out["ui"] = 200 <= response.status_code < 400
        except httpx.HTTPError:
            out["ui"] = False
    return out
