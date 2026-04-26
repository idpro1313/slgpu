"""Schemas for /api/v1/jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    correlation_id: str
    kind: str
    scope: str
    resource: str | None
    status: JobStatus
    command: list[str]
    args: dict[str, Any] = Field(default_factory=dict)
    actor: str | None
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    stdout_tail: str | None
    stderr_tail: str | None
    progress: float | None
    message: str | None
    created_at: datetime
    updated_at: datetime
