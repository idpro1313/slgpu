"""Persistent settings used by the web UI."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.stack_config import ports_for_probes_sync, sync_merged_flat
from app.services.stack_errors import MissingStackParams
from app.core.security import ValidationError
from app.models.setting import Setting

PUBLIC_ACCESS_KEY = "public_access"
_HOST_RE = re.compile(r"^(localhost|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")
_INTERNAL_HOSTS = {"host.docker.internal"}


async def get_public_access_value(session: AsyncSession) -> dict[str, Any]:
    result = await session.execute(select(Setting).where(Setting.key == PUBLIC_ACCESS_KEY))
    setting = result.scalar_one_or_none()
    if setting is None or not isinstance(setting.value, dict):
        return {}
    return dict(setting.value)


async def set_public_access_value(session: AsyncSession, value: dict[str, Any]) -> None:
    result = await session.execute(select(Setting).where(Setting.key == PUBLIC_ACCESS_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(key=PUBLIC_ACCESS_KEY, value={})
        session.add(setting)
    setting.value = value
    await session.flush()


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
    raw = (await get_public_access_value(session)).get("server_host")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return normalize_server_host(raw)


async def get_litellm_api_key(session: AsyncSession) -> str | None:
    raw = (await get_public_access_value(session)).get("litellm_api_key")
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if s else None


async def get_litellm_master_key(session: AsyncSession) -> str | None:
    raw = (await get_public_access_value(session)).get("litellm_master_key")
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return s if s else None


async def set_public_server_host(session: AsyncSession, server_host: str | None) -> str | None:
    normalized = normalize_server_host(server_host)
    d = await get_public_access_value(session)
    if normalized:
        d["server_host"] = normalized
    else:
        d.pop("server_host", None)
    await set_public_access_value(session, d)
    return normalized


def effective_server_host(
    request: Request,
    configured_host: str | None,
    merged: dict[str, str] | None,
) -> str:
    """Публичный host для ссылок. Без молчаливого ``127.0.0.1``: fallback — ``WEB_PUBLIC_HOST`` из стека."""
    if configured_host:
        return configured_host
    request_host = request.url.hostname
    if request_host and request_host not in _INTERNAL_HOSTS:
        return request_host
    if merged is None:
        return request_host or "localhost"
    pub = (merged.get("WEB_PUBLIC_HOST") or "").strip()
    if pub:
        return pub
    raise MissingStackParams(["WEB_PUBLIC_HOST"], "probes")


def public_urls(server_host: str) -> dict[str, str]:
    p = ports_for_probes_sync()
    prom = int(p["prometheus_port"])
    graf = int(p["grafana_port"])
    lf = int(p["langfuse_port"])
    llm = int(p["litellm_port"])
    return {
        "prometheus": f"http://{server_host}:{prom}",
        "grafana": f"http://{server_host}:{graf}",
        "langfuse": f"http://{server_host}:{lf}",
        "litellm": f"http://{server_host}:{llm}/ui",
        "litellm_api": f"http://{server_host}:{llm}/v1",
    }


async def get_public_urls(session: AsyncSession, request: Request) -> dict[str, str]:
    configured = await get_public_server_host(session)
    try:
        merged = sync_merged_flat()
    except RuntimeError:
        merged = None
    return public_urls(effective_server_host(request, configured, merged))
