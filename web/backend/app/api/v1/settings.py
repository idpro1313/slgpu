"""User-editable web UI settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.security import ValidationError
from app.schemas.settings import PublicAccessSettings, PublicAccessSettingsUpdate
from app.services import app_settings
from app.services.stack_config import sync_merged_flat
from app.services.ui_audit import record_ui_action

router = APIRouter()


@router.get("/public-access", response_model=PublicAccessSettings)
async def get_public_access(
    request: Request,
    session: AsyncSession = Depends(db_session),
) -> PublicAccessSettings:
    configured_host = await app_settings.get_public_server_host(session)
    try:
        merged = sync_merged_flat()
    except RuntimeError:
        merged = None
    effective_host = app_settings.effective_server_host(
        request, configured_host, merged
    )
    urls = app_settings.public_urls(effective_host)
    key_set = (await app_settings.get_litellm_api_key(session)) is not None
    master_key_set = (await app_settings.get_litellm_master_key(session)) is not None
    return PublicAccessSettings(
        server_host=configured_host,
        effective_server_host=effective_host,
        grafana_url=urls["grafana"],
        prometheus_url=urls["prometheus"],
        langfuse_url=urls["langfuse"],
        litellm_ui_url=urls["litellm"],
        litellm_api_url=urls["litellm_api"],
        litellm_api_key_set=key_set,
        litellm_master_key_set=master_key_set,
    )


@router.patch("/public-access", response_model=PublicAccessSettings)
async def update_public_access(
    payload: PublicAccessSettingsUpdate,
    request: Request,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> PublicAccessSettings:
    body = payload.model_dump(exclude_unset=True)
    if "server_host" in body:
        try:
            await app_settings.set_public_server_host(session, body.get("server_host"))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    key_updated = False
    if "litellm_api_key" in body:
        d = await app_settings.get_public_access_value(session)
        lk = body["litellm_api_key"]
        if lk is None or (isinstance(lk, str) and not str(lk).strip()):
            d.pop("litellm_api_key", None)
        else:
            d["litellm_api_key"] = str(lk).strip()[:2000]
        await app_settings.set_public_access_value(session, d)
        key_updated = True
    master_key_updated = False
    if "litellm_master_key" in body:
        d = await app_settings.get_public_access_value(session)
        mk = body["litellm_master_key"]
        if mk is None or (isinstance(mk, str) and not str(mk).strip()):
            d.pop("litellm_master_key", None)
        else:
            d["litellm_master_key"] = str(mk).strip()[:2000]
        await app_settings.set_public_access_value(session, d)
        master_key_updated = True
    await record_ui_action(
        session,
        action="settings.public_access",
        actor=actor,
        target="public_access",
        note=(
            "[settings][update_public_access][BLOCK_KEY_ROTATED] litellm keys"
            if key_updated or master_key_updated
            else "public links / LiteLLM API settings"
        ),
        payload={
            "server_host": body.get("server_host") if "server_host" in body else None,
            "litellm_api_key_updated": key_updated,
            "litellm_master_key_updated": master_key_updated,
        },
    )
    return await get_public_access(request=request, session=session)
