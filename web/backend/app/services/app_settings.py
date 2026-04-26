"""Persistent settings used by the web UI."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ValidationError
from app.models.setting import Setting

PUBLIC_ACCESS_KEY = "public_access"
_HOST_RE = re.compile(r"^(localhost|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")
_INTERNAL_HOSTS = {"host.docker.internal"}


def normalize_server_host(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if "://" in candidate:
        parsed = urlsplit(candidate)
        candidate = parsed.hostname or ""
    else:
        candidate = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if ":" in candidate and not candidate.startswith("["):
            candidate = candidate.split(":", 1)[0]
    candidate = candidate.strip().strip("[]").lower()
    if not candidate:
        return None
    if not _HOST_RE.match(candidate) or ".." in candidate:
        raise ValidationError("server_host must be a hostname or IP address, without path")
    return candidate


async def get_public_server_host(session: AsyncSession) -> str | None:
    result = await session.execute(select(Setting).where(Setting.key == PUBLIC_ACCESS_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        return None
    raw = setting.value.get("server_host")
    return normalize_server_host(raw if isinstance(raw, str) else None)


async def set_public_server_host(session: AsyncSession, server_host: str | None) -> str | None:
    normalized = normalize_server_host(server_host)
    result = await session.execute(select(Setting).where(Setting.key == PUBLIC_ACCESS_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(key=PUBLIC_ACCESS_KEY, value={})
        session.add(setting)
    setting.value = {"server_host": normalized} if normalized else {}
    await session.flush()
    return normalized


def effective_server_host(request: Request, configured_host: str | None) -> str:
    if configured_host:
        return configured_host
    request_host = request.url.hostname
    if request_host and request_host not in _INTERNAL_HOSTS:
        return request_host
    settings = get_settings()
    if settings.monitoring_http_host not in _INTERNAL_HOSTS:
        return settings.monitoring_http_host
    return "127.0.0.1"


def public_urls(server_host: str) -> dict[str, str]:
    settings = get_settings()
    return {
        "prometheus": f"http://{server_host}:{settings.prometheus_port}",
        "grafana": f"http://{server_host}:{settings.grafana_port}",
        "langfuse": f"http://{server_host}:{settings.langfuse_port}",
        "litellm": f"http://{server_host}:{settings.litellm_port}/ui",
        "litellm_api": f"http://{server_host}:{settings.litellm_port}/v1",
    }


async def get_public_urls(session: AsyncSession, request: Request) -> dict[str, str]:
    configured = await get_public_server_host(session)
    return public_urls(effective_server_host(request, configured))
