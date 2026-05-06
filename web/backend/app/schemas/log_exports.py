"""Схемы API выгрузки логов из Loki в файл."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LogExportCreate(BaseModel):
    time_from: datetime
    time_to: datetime
    scope: str = Field(description="slgpu | all | custom")
    logql: str | None = Field(default=None, description="При scope=custom — полный LogQL-селектор {…}")
    redact_secrets: bool = True
    container: str | None = Field(default=None, max_length=256)
    compose_service: str | None = Field(default=None, max_length=256)
    compose_project: str | None = Field(default=None, max_length=256)
    slgpu_slot: str | None = Field(default=None, max_length=256)
    slgpu_engine: str | None = Field(default=None, max_length=64)
    slgpu_preset: str | None = Field(default=None, max_length=256)
    slgpu_run_id: str | None = Field(default=None, max_length=128)

    @field_validator(
        "container",
        "compose_service",
        "compose_project",
        "slgpu_slot",
        "slgpu_engine",
        "slgpu_preset",
        "slgpu_run_id",
        "logql",
        mode="before",
    )
    @classmethod
    def _strip_opt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("scope", mode="before")
    @classmethod
    def _scope_norm(cls, v: str) -> str:
        s = str(v).strip().lower()
        if s not in ("slgpu", "all", "custom"):
            raise ValueError("scope must be slgpu, all, or custom")
        return s


class LogExportAccepted(BaseModel):
    export_id: int
    job_id: int
    correlation_id: str
    message: str | None = None


class LogExportOut(BaseModel):
    id: int
    status: str
    job_id: int | None
    time_from: datetime
    time_to: datetime
    scope: str
    logql: str | None
    redact_secrets: bool
    artifact_relpath: str | None
    line_count: int | None
    byte_size: int | None
    retention_note: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LogExportsListOut(BaseModel):
    items: list[LogExportOut]
