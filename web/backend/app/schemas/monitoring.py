"""Schemas for /api/v1/monitoring and /api/v1/litellm."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.service import ServiceStatus


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str
    category: str
    status: ServiceStatus
    container_id: str | None
    url: str | None
    detail: str | None
    extra: dict[str, Any]
    last_seen_at: datetime | None


class StackActionRequest(BaseModel):
    action: str
