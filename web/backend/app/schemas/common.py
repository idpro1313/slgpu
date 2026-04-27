"""Generic response wrappers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    slgpu_root: str
    database_url_masked: str


class MessageResponse(BaseModel):
    message: str
    detail: dict[str, Any] | None = None


class JobAccepted(BaseModel):
    job_id: int
    correlation_id: str
    kind: str
    status: str
    message: str | None = None
    # POST /runtime/slots/{key}/down?force=1 — немедленный stop, без новой job
    forced: bool = False
    cancelled_job_ids: list[int] = []
