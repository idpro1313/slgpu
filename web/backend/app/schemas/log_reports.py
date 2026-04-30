"""Pydantic schemas for POST/GET /api/v1/log-reports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LogReportCreate(BaseModel):
    """Request body for starting a new report job."""

    time_from: datetime = Field(description="Интервал начала (UTC-aware предпочтительно).")
    time_to: datetime = Field(description="Интервал конца.")
    scope: Literal["slgpu", "all", "custom"] = Field(
        default="slgpu",
        description="slgpu — контейнеры slgpu-* / monitoring / proxy; all — job=docker-logs; custom — поле logql.",
    )
    logql: str | None = Field(
        default=None,
        description="Обязательно при scope=custom; иначе игнорируется.",
        max_length=4096,
    )
    llm_model: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Имя модели в LiteLLM (как в /v1/chat/completions).",
    )
    max_lines: int = Field(
        default=8000,
        ge=500,
        le=20_000,
        description="Максимум строк логов, извлекаемых из Loki до агрегации.",
    )


class LogReportAccepted(BaseModel):
    report_id: int
    job_id: int
    correlation_id: str
    status: Literal["pending"] = "pending"
    message: str | None = None


class LogReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    job_id: int | None
    time_from: datetime
    time_to: datetime
    scope: str
    logql: str | None
    llm_model: str
    max_lines: int
    facts: dict | None = None
    llm_markdown: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class LogReportsListOut(BaseModel):
    items: list[LogReportOut]
