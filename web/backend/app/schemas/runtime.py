"""Schemas for /api/v1/runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.run import RunStatus


class EngineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    engine: str
    preset_name: str | None
    api_port: int | None
    tp: int | None
    gpu_mask: str | None
    desired_status: RunStatus
    observed_status: RunStatus
    container_id: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    last_error: str | None
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EngineUpRequest(BaseModel):
    engine: str = Field(examples=["vllm", "sglang"])
    preset: str
    port: int | None = None
    tp: int | None = None


class EngineRestartRequest(BaseModel):
    preset: str
    tp: int | None = None


class EngineDownRequest(BaseModel):
    include_monitoring: bool = False


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
