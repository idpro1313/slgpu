"""Schemas for /api/v1/runtime."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

class RuntimeSlotView(BaseModel):
    """One inference slot: runtime probe + optional DB join."""

    slot_key: str
    engine: str
    preset_name: str | None = None
    hf_id: str | None = None
    api_port: int | None = None
    tp: int | None = None
    gpu_indices: str | None = None
    container_status: str | None = None
    container_name: str | None = None
    served_models: list[str] = Field(default_factory=list)
    metrics_available: bool = False


class RuntimeSnapshot(BaseModel):
    engine: str | None
    api_port: int | None
    container_status: str | None
    preset_name: str | None = None
    hf_id: str | None = None
    tp: int | None = None
    served_models: list[str] = Field(default_factory=list)
    metrics_available: bool = False
    last_checked_at: datetime | None
    slots: list[RuntimeSlotView] = Field(default_factory=list)


class RuntimeLogs(BaseModel):
    engine: str | None
    container_name: str | None
    container_status: str | None
    tail: int
    logs: str
    last_checked_at: datetime | None
