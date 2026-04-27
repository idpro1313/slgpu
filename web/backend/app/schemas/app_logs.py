"""Схемы API структурированного журнала приложения (таблица ``app_log_event``)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AppLogEventOut(BaseModel):
    """Одна строка журнала."""

    id: int
    created_at: datetime
    updated_at: datetime
    level: str
    logger_name: str
    event_kind: str
    message: str
    http_method: str | None = None
    http_path: str | None = None
    query_hint: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    module_anchor: str | None = None
    log_extra: dict | None = None
    exc_summary: str | None = None

    model_config = {"from_attributes": True}


class AppLogEventsListOut(BaseModel):
    items: list[AppLogEventOut]
    next_before_id: int | None = Field(
        default=None,
        description="Курсор для следующей страницы: передать как `before_id`, если не null.",
    )
