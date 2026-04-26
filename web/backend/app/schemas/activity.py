"""Объединённая лента: CLI-задачи (jobs) и действия UI (audit_events без correlation_id)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.jobs import JobOut


class ActivityJobItem(BaseModel):
    type: Literal["job"] = "job"
    created_at: datetime
    job: JobOut

    model_config = ConfigDict(from_attributes=False)


class ActivityUiItem(BaseModel):
    type: Literal["ui"] = "ui"
    created_at: datetime
    audit_id: int
    action: str
    target: str | None
    actor: str | None
    note: str | None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=False)
