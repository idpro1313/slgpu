"""Schemas for /api/v1/presets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    model_id: int | None
    hf_id: str
    tp: int | None
    gpu_mask: str | None
    served_model_name: str | None
    parameters: dict[str, Any]
    file_path: str | None
    is_synced: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    hf_id: str
    tp: int | None = None
    gpu_mask: str | None = None
    served_model_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class PresetUpdate(BaseModel):
    description: str | None = None
    hf_id: str | None = None
    tp: int | None = None
    gpu_mask: str | None = None
    served_model_name: str | None = None
    parameters: dict[str, Any] | None = None
    is_active: bool | None = None


class PresetSyncResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


class PresetImportTemplatesResult(BaseModel):
    """Копирование ``examples/presets/*.env`` в PRESETS_DIR и импорт в БД (как ``POST /presets/sync``)."""

    files_copied: int
    files_skipped_existing: int
    imported: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
