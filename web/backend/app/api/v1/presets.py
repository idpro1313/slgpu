"""Preset CRUD and synchronisation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.security import (
    ValidationError,
    validate_hf_id,
    validate_slug,
    validate_tp,
)
from app.models.preset import Preset
from app.schemas.presets import PresetCreate, PresetOut, PresetSyncResult, PresetUpdate
from app.services import presets as preset_service
from app.services.ui_audit import record_ui_action

router = APIRouter()


@router.get("", response_model=list[PresetOut])
async def list_presets(session: AsyncSession = Depends(db_session)) -> list[Preset]:
    result = await session.execute(select(Preset).order_by(Preset.name))
    return list(result.scalars().all())


@router.post("/sync", response_model=PresetSyncResult)
async def sync_presets(
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> PresetSyncResult:
    imported, updated, skipped, errors = await preset_service.import_files_into_db(session)
    await record_ui_action(
        session,
        action="presets.sync",
        actor=actor,
        target=None,
        note=f"imported={imported} updated={updated} skipped={skipped} errors={len(errors)}",
        payload={"imported": imported, "updated": updated, "skipped": skipped, "error_lines": errors[:20]},
    )
    return PresetSyncResult(imported=imported, updated=updated, skipped=skipped, errors=errors)


@router.post("", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
async def create_preset(
    payload: PresetCreate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> Preset:
    try:
        validate_slug(payload.name)
        validate_hf_id(payload.hf_id)
        if payload.tp is not None:
            validate_tp(payload.tp)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = await session.execute(select(Preset).where(Preset.name == payload.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="preset with this name already exists")

    preset = Preset(
        name=payload.name,
        description=payload.description,
        hf_id=payload.hf_id,
        tp=payload.tp,
        gpu_mask=payload.gpu_mask,
        served_model_name=payload.served_model_name,
        parameters=payload.parameters,
        is_active=True,
        is_synced=False,
    )
    session.add(preset)
    await session.flush()
    await record_ui_action(
        session,
        action="preset.create",
        actor=actor,
        target=payload.name,
        note=f"hf_id={payload.hf_id}",
        payload={"name": payload.name, "hf_id": payload.hf_id},
    )
    return preset


@router.get("/{preset_id}", response_model=PresetOut)
async def get_preset(preset_id: int, session: AsyncSession = Depends(db_session)) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    return preset


@router.patch("/{preset_id}", response_model=PresetOut)
async def update_preset(
    preset_id: int,
    payload: PresetUpdate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    fields = payload.model_fields_set
    if "hf_id" in fields and payload.hf_id is not None:
        try:
            validate_hf_id(payload.hf_id)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        preset.hf_id = payload.hf_id
    if "tp" in fields:
        if payload.tp is None:
            preset.tp = None
        else:
            try:
                validate_tp(payload.tp)
            except ValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            preset.tp = payload.tp
    if "description" in fields:
        preset.description = payload.description
    if "gpu_mask" in fields:
        preset.gpu_mask = payload.gpu_mask
    if "served_model_name" in fields:
        preset.served_model_name = payload.served_model_name
    if "parameters" in fields:
        preset.parameters = payload.parameters or {}
    if "is_active" in fields and payload.is_active is not None:
        preset.is_active = payload.is_active
    preset.is_synced = False
    await record_ui_action(
        session,
        action="preset.update",
        actor=actor,
        target=preset.name,
        note="patch preset",
        payload={"preset_id": preset_id, "fields": list(fields)},
    )
    return preset


@router.post("/{preset_id}/export", response_model=PresetOut)
async def export_preset(
    preset_id: int,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    try:
        path = await preset_service.export_preset_to_file(session, preset)
    except (OSError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"export failed: {exc}") from exc
    await record_ui_action(
        session,
        action="preset.export",
        actor=actor,
        target=preset.name,
        note=str(path) if path else None,
        payload={"preset_id": preset_id, "name": preset.name},
    )
    return preset


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    delete_file: bool = False,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> dict[str, object]:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    name = preset.name
    deleted_file = None
    if delete_file and preset.file_path:
        path = Path(preset.file_path).resolve()
        allowed_dir = preset_service.presets_dir().resolve()
        try:
            path.relative_to(allowed_dir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="preset file is outside PRESETS_DIR") from exc
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"delete file failed: {exc}") from exc
            deleted_file = str(path)
    await record_ui_action(
        session,
        action="preset.delete",
        actor=actor,
        target=name,
        note=f"delete_file={delete_file}",
        payload={"preset_id": preset_id, "name": name, "delete_file": delete_file},
    )
    await session.delete(preset)
    return {"deleted": True, "deleted_file": deleted_file}
