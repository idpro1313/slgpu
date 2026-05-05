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


class PresetCloneRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    hf_id: str | None = None
    tp: int | None = None
    gpu_mask: str | None = None
    served_model_name: str | None = None
    parameters: dict[str, Any] | None = None


class PresetParameterSchemaRow(BaseModel):
    """Один поддерживаемый ключ `presets.parameters` для UI (значение по умолчанию — подсказка из serve.sh)."""

    key: str
    group: str
    default_value: str = ""
    description: str = ""


class PresetParameterSchemaOut(BaseModel):
    rows: list[PresetParameterSchemaRow]
