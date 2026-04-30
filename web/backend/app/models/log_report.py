"""On-demand aggregated log report over Loki + optional LLM narrative."""

from __future__ import annotations

import enum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LogReportStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LogReport(Base):
    """Stores parameters, deterministic facts, and LiteLLM-produced Markdown."""

    __tablename__ = "log_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    status: Mapped[LogReportStatus] = mapped_column(
        Enum(LogReportStatus),
        default=LogReportStatus.PENDING,
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
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    max_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=8000)

    facts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
