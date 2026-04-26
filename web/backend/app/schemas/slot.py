"""Inference slot API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.slot import RunStatus


class EngineSlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slot_key: str
    engine: str
    preset_name: str | None
    hf_id: str | None
    tp: int | None
    gpu_indices: str | None
    host_api_port: int | None
    internal_api_port: int | None
    container_id: str | None
    container_name: str | None
    desired_status: RunStatus
    observed_status: RunStatus
    last_error: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime
    extra: dict = Field(default_factory=dict)


class SlotCreateRequest(BaseModel):
    """Launch a new slot; auto GPU/port when omitted (server computes)."""

    slot_key: str | None = None
    engine: Literal["vllm", "sglang"] = "vllm"
    preset: str
    host_api_port: int | None = None
    tp: int | None = None
    gpu_indices: list[int] | None = None


class SlotRestartRequest(BaseModel):
    preset: str
    host_api_port: int | None = None
    tp: int | None = None
    gpu_indices: list[int] | None = None
