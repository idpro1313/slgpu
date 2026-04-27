"""Install from main.env / CRUD stack config in SQLite (replaces web reading main.env)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.services.stack_config import (
    META_KEY,
    mask_secrets,
    merge_partial_secrets,
    parse_dotenv_text,
    split_stack_and_secrets,
)
from app.services import stack_config as sc
from app.services import presets as preset_service
from app.services.env_key_aliases import presentation_stack
from app.services.stack_registry import (
    StackScope,
    registry_to_public,
    validate_required,
)

router = APIRouter()


class InstallRequest(BaseModel):
    force: bool = False


class InstallResult(BaseModel):
    installed: bool
    stack_keys: int
    secret_keys: int


@router.get("/status")
async def install_status(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    _, _, meta = await sc.load_sections(session)
    return {"installed": bool(meta.get("installed")), "meta": meta}


@router.post("/install", response_model=InstallResult)
async def install_from_files(
    payload: InstallRequest,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> InstallResult:
    settings = get_settings()
    root = settings.slgpu_root
    _, _, meta = await sc.load_sections(session)
    if meta.get("installed") and not payload.force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already installed; use force=true to re-import",
        )

    main = root / "configs" / "main.env"
    if not main.is_file():
        raise HTTPException(status_code=400, detail=f"missing {main}")

    flat = parse_dotenv_text(main.read_text(encoding="utf-8"))

    stack, secrets = split_stack_and_secrets(flat)
    await sc.replace_all_params_from_flat(session, flat)
    pdir = root / "data" / "presets"
    await preset_service.import_presets_from_disk(session, pdir)
    await sc.save_section(
        session,
        META_KEY,
        {
            "installed": True,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source": "configs/main.env",
        },
    )
    session.add(
        AuditEvent(
            actor=actor,
            action="app_config.install",
            target="stack",
            correlation_id=None,
            payload={"stack_keys": len(stack), "secret_keys": len(secrets)},
            note="install from files",
        )
    )
    return InstallResult(
        installed=True,
        stack_keys=len(stack),
        secret_keys=len(secrets),
    )


_ALLOWED_SCOPES: tuple[StackScope, ...] = (
    "web_up",
    "monitoring_up",
    "proxy_up",
    "llm_slot",
    "fix_perms",
    "pull",
    "bench",
    "port_allocation",
)


@router.get("/missing")
async def get_missing(
    scope: str | None = None,
    session: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    """Return registry keys missing in DB for the given scope (or all scopes)."""
    await sc.migrate_stack_params_to_canonical_if_needed(session)
    stack, secrets, _meta = await sc.load_sections(session)
    merged: dict[str, str] = {**dict(stack), **dict(secrets)}
    if scope is not None:
        if scope not in _ALLOWED_SCOPES:
            raise HTTPException(status_code=400, detail=f"unknown scope: {scope}")
        return {"scope": scope, "missing": validate_required(merged, scope)}
    by_scope: dict[str, list[dict[str, Any]]] = {}
    for s in _ALLOWED_SCOPES:
        by_scope[s] = list(validate_required(merged, s))
    return {"scopes": by_scope}


@router.get("/stack")
async def get_stack(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    await sc.migrate_stack_params_to_canonical_if_needed(session)
    stack, secrets, meta = await sc.load_sections(session)
    return {
        "stack": presentation_stack(stack),
        "secrets": mask_secrets(secrets),
        "meta": meta,
        "registry": registry_to_public(),
    }


@router.patch("/stack")
async def patch_stack(
    payload: dict[str, Any],
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> dict[str, Any]:
    stack, secrets, _meta = await sc.load_sections(session)
    if "stack" in payload and isinstance(payload["stack"], dict):
        for k, v in payload["stack"].items():
            key = str(k)
            if v is None:
                await sc.delete_stack_param(session, key)
            else:
                await sc.upsert_stack_param(session, key, str(v))
    if "secrets" in payload and isinstance(payload["secrets"], dict):
        _, secrets, _ = await sc.load_sections(session)
        secrets = merge_partial_secrets(
            {str(k): str(v) for k, v in secrets.items()},
            {str(k): v for k, v in payload["secrets"].items()},
        )
        await sc.replace_secret_params(session, secrets)
    await sc.migrate_stack_params_to_canonical_if_needed(session)
    stack, secrets, _ = await sc.load_sections(session)
    session.add(
        AuditEvent(
            actor=actor,
            action="app_config.patch",
            target="stack",
            correlation_id=None,
            payload={"keys": list(payload.keys())},
            note="patch stack/secrets",
        )
    )
    return {
        "ok": True,
        "stack": presentation_stack(stack),
        "secrets": mask_secrets(secrets),
    }
