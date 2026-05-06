"""Фоновая выгрузка полных контейнерных логов из Loki в файл (ndjson.gz)."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LogExportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LogExport(Base):
    __tablename__ = "log_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    status: Mapped[LogExportStatus] = mapped_column(
        Enum(LogExportStatus),
        default=LogExportStatus.PENDING,
        nullable=False,
        index=True,
    )
    job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    time_from: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    time_to: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    scope: Mapped[str] = mapped_column(Text, nullable=False)
    logql: Mapped[str | None] = mapped_column(Text, nullable=True)
    redact_secrets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    artifact_relpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
