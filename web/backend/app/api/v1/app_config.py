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
    SECRETS_KEY,
    STACK_KEY,
    mask_secrets,
    merge_partial_secrets,
    parse_dotenv_text,
    split_stack_and_secrets,
)
from app.services import stack_config as sc

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

    main = root / "main.env"
    if not main.is_file():
        raise HTTPException(status_code=400, detail=f"missing {main}")

    flat = parse_dotenv_text(main.read_text(encoding="utf-8"))
    hf = root / "configs" / "secrets" / "hf.env"
    if hf.is_file():
        flat.update(parse_dotenv_text(hf.read_text(encoding="utf-8")))
    lf = root / "configs" / "secrets" / "langfuse-litellm.env"
    if lf.is_file():
        flat.update(parse_dotenv_text(lf.read_text(encoding="utf-8")))

    stack, secrets = split_stack_and_secrets(flat)
    await sc.save_section(session, STACK_KEY, stack)
    await sc.save_section(session, SECRETS_KEY, secrets)
    await sc.save_section(
        session,
        META_KEY,
        {
            "installed": True,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source": "main.env+secrets",
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


@router.get("/stack")
async def get_stack(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    stack, secrets, meta = await sc.load_sections(session)
    return {
        "stack": stack,
        "secrets": mask_secrets(secrets),
        "meta": meta,
    }


@router.patch("/stack")
async def patch_stack(
    payload: dict[str, Any],
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> dict[str, Any]:
    stack, secrets, _meta = await sc.load_sections(session)
    if "stack" in payload and isinstance(payload["stack"], dict):
        stack.update({k: str(v) for k, v in payload["stack"].items() if v is not None})
        await sc.save_section(session, STACK_KEY, stack)
    if "secrets" in payload and isinstance(payload["secrets"], dict):
        secrets = merge_partial_secrets(
            {str(k): str(v) for k, v in secrets.items()},
            {str(k): v for k, v in payload["secrets"].items()},
        )
        await sc.save_section(session, SECRETS_KEY, secrets)
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
    return {"ok": True, "stack": stack, "secrets": mask_secrets(secrets)}
