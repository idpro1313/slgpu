"""GPU live state and availability for the web UI."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.gpu import (
    BusyGpuView,
    GpuAvailabilityResponse,
    GpuStateResponse,
)
from app.services import gpu_availability
from app.services import gpu_state

router = APIRouter()


@router.get("/state", response_model=GpuStateResponse)
async def get_gpu_state() -> GpuStateResponse:
    raw = await gpu_state.get_gpu_state_snapshot()
    return GpuStateResponse(
        smi_available=raw.get("available", False),
        error=raw.get("error"),
        driver_version=raw.get("driver_version"),
        cuda_version=raw.get("cuda_version"),
        gpus=raw.get("gpus", []),
        processes=raw.get("processes", []),
    )


@router.get("/availability", response_model=GpuAvailabilityResponse)
async def get_gpu_availability(
    tp: int = Query(1, ge=1, le=128),
    exclude_slot: str | None = Query(None, description="Ignore reservation by this slot_key"),
) -> GpuAvailabilityResponse:
    data = await gpu_availability.compute_availability(tp=tp, exclude_slot_key=exclude_slot)
    busy = [
        BusyGpuView(
            index=b["index"],
            slot_key=b["slot_key"],
            preset_name=b.get("preset_name"),
            engine=b["engine"],
        )
        for b in data.get("busy", [])
    ]
    return GpuAvailabilityResponse(
        all_indices=list(data.get("all_indices", [])),
        available=list(data.get("available", [])),
        busy=busy,
        suggested=data.get("suggested"),
        note=data.get("note"),
    )
