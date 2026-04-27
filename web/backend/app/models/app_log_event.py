"""Структурированные события журнала приложения (UI «Логи»)."""

from __future__ import annotations

from sqlalchemy import Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from app.db.base import Base

# GRACE [M-WEB][app_log_event][BLOCK_APP_LOG_EVENT]


class AppLogEvent(Base):
    """Событие `app.log`: HTTP, логгеры, traceback (усечённый). Не путать с `audit_events`."""

    __tablename__ = "app_log_event"
    __table_args__ = (
        Index("ix_app_log_event_level_created", "level", "created_at"),
        Index("ix_app_log_event_kind_created", "event_kind", "created_at"),
        Index("ix_app_log_event_path_created", "http_path", "created_at"),
        Index("ix_app_log_event_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    logger_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(2000), nullable=False)
    http_method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    http_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    query_hint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    module_anchor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    log_extra: Mapped[dict | None] = mapped_column("log_extra", JSON, nullable=True)
    exc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
