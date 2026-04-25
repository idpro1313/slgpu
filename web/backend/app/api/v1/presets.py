"""Preset CRUD and synchronisation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.core.security import ValidationError, validate_engine, validate_slug, validate_tp
from app.models.preset import Preset
from app.schemas.presets import PresetCreate, PresetOut, PresetSyncResult, PresetUpdate
from app.services import presets as preset_service

router = APIRouter()


@router.get("", response_model=list[PresetOut])
async def list_presets(session: AsyncSession = Depends(db_session)) -> list[Preset]:
    result = await session.execute(select(Preset).order_by(Preset.name))
    return list(result.scalars().all())


@router.post("/sync", response_model=PresetSyncResult)
async def sync_presets(session: AsyncSession = Depends(db_session)) -> PresetSyncResult:
    imported, updated, skipped, errors = await preset_service.import_files_into_db(session)
    return PresetSyncResult(imported=imported, updated=updated, skipped=skipped, errors=errors)


@router.post("", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
async def create_preset(payload: PresetCreate, session: AsyncSession = Depends(db_session)) -> Preset:
    try:
        validate_slug(payload.name)
        validate_engine(payload.engine)
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
        engine=payload.engine,
        tp=payload.tp,
        gpu_mask=payload.gpu_mask,
        served_model_name=payload.served_model_name,
        parameters=payload.parameters,
        is_active=True,
        is_synced=False,
    )
    session.add(preset)
    await session.flush()
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
) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    if payload.engine is not None:
        try:
            validate_engine(payload.engine)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        preset.engine = payload.engine
    if payload.tp is not None:
        try:
            validate_tp(payload.tp)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        preset.tp = payload.tp
    if payload.description is not None:
        preset.description = payload.description
    if payload.gpu_mask is not None:
        preset.gpu_mask = payload.gpu_mask
    if payload.served_model_name is not None:
        preset.served_model_name = payload.served_model_name
    if payload.parameters is not None:
        preset.parameters = payload.parameters
    if payload.is_active is not None:
        preset.is_active = payload.is_active
    preset.is_synced = False
    return preset


@router.post("/{preset_id}/export", response_model=PresetOut)
async def export_preset(preset_id: int, session: AsyncSession = Depends(db_session)) -> Preset:
    preset = await session.get(Preset, preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    try:
        await preset_service.export_preset_to_file(session, preset)
    except (OSError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail=f"export failed: {exc}") from exc
    return preset
