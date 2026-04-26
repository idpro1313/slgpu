"""User-editable web UI settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.security import ValidationError
from app.schemas.settings import PublicAccessSettings, PublicAccessSettingsUpdate
from app.services import app_settings
from app.services.ui_audit import record_ui_action

router = APIRouter()


@router.get("/public-access", response_model=PublicAccessSettings)
async def get_public_access(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> PublicAccessSettings:
    configured_host = await app_settings.get_public_server_host(session)
    effective_host = app_settings.effective_server_host(request, configured_host)
    urls = app_settings.public_urls(effective_host)
    return PublicAccessSettings(
        server_host=configured_host,
        effective_server_host=effective_host,
        grafana_url=urls["grafana"],
        prometheus_url=urls["prometheus"],
        langfuse_url=urls["langfuse"],
        litellm_ui_url=urls["litellm"],
        litellm_api_url=urls["litellm_api"],
    )


@router.patch("/public-access", response_model=PublicAccessSettings)
async def update_public_access(
    payload: PublicAccessSettingsUpdate,
    request: Request,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> PublicAccessSettings:
    try:
        await app_settings.set_public_server_host(session, payload.server_host)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_ui_action(
        session,
        action="settings.public_access",
        actor=actor,
        target="server_host",
        note="public links host",
        payload={"server_host": payload.server_host},
    )
    return await get_public_access(request=request, session=session)
