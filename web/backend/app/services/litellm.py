"""Read-only adapter for the LiteLLM Admin API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import app_settings
from app.services.stack_config import sync_merged_flat

logger = logging.getLogger(__name__)


def litellm_http_base_sync() -> str:
    """Публичный базовый URL к LiteLLM внутри сети Docker (как probes)."""

    return _litellm_http_probe_base()


def _litellm_http_probe_base() -> str:
    """Базовый URL slgpu-web → LiteLLM по сети ``slgpu`` (Docker DNS alias ``LITELLM_SERVICE_NAME``).

    Не используем ``WEB_MONITORING_HTTP_HOST`` + published port: при ``LITELLM_BIND=127.0.0.1``
    порт на хосте слушает только loopback и с других контейнеров через ``host.docker.internal``
    недоступен — ``GET /v1/models`` и health давали ``[litellm][list_models][BLOCK_HTTP_ERROR]``.
    """
    m = sync_merged_flat()
    host = str(m.get("LITELLM_SERVICE_NAME") or "").strip()
    if not host:
        raise RuntimeError("missing stack param LITELLM_SERVICE_NAME")
    try:
        port = int(m["LITELLM_PORT"])
    except KeyError as exc:
        raise RuntimeError("missing stack param LITELLM_PORT") from exc
    except ValueError as exc:
        raise RuntimeError("invalid LITELLM_PORT") from exc
    return f"http://{host}:{port}"


async def _bearer_headers(session: AsyncSession | None) -> dict[str, str]:
    if session is None:
        return {}
    key = await app_settings.get_litellm_api_key(session)
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


async def list_models(session: AsyncSession | None = None) -> list[dict[str, Any]]:
    base = _litellm_http_probe_base()
    url = f"{base}/v1/models"
    headers = await _bearer_headers(session)
    async with httpx.AsyncClient(timeout=3.0, headers=headers) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                return []
            return response.json().get("data", [])
        except httpx.HTTPError as exc:
            logger.warning("[litellm][list_models][BLOCK_HTTP_ERROR] %s", exc)
            return []


async def health(session: AsyncSession | None = None) -> dict[str, Any]:
    base = _litellm_http_probe_base()
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
