"""API schemas for /api/v1/gpu/*."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GpuProcessView(BaseModel):
    pid: int
    used_memory_mib: int | str
    process_name: str = ""
    gpu_uuid: str | None = None
    slot_key: str | None = None
    container_name: str | None = None


class GpuCardView(BaseModel):
    index: int
    uuid: str | None = None
    name: str = ""
    memory_used_mib: int | str = 0
    memory_total_mib: int | str = 0
    utilization_gpu: int | str = 0
    utilization_memory: int | str = 0
    processes: list[dict[str, Any]] = Field(default_factory=list)


class GpuStateResponse(BaseModel):
    smi_available: bool = False
    error: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    gpus: list[dict[str, Any]] = Field(default_factory=list)
    processes: list[dict[str, Any]] = Field(default_factory=list)


class BusyGpuView(BaseModel):
    index: int
    slot_key: str
    preset_name: str | None
    engine: str


class GpuAvailabilityResponse(BaseModel):
    all_indices: list[int] = Field(default_factory=list)
    available: list[int] = Field(default_factory=list)
    busy: list[BusyGpuView] = Field(default_factory=list)
    suggested: list[int] | None = None
    note: str | None = None
