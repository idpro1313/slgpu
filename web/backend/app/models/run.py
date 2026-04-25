"""Engine run desired state and observed snapshot."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunStatus(str, enum.Enum):
    REQUESTED = "requested"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"


class EngineRun(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    preset_name: Mapped[str | None] = mapped_column(String(128))
    api_port: Mapped[int | None] = mapped_column(Integer)
    tp: Mapped[int | None] = mapped_column(Integer)
    gpu_mask: Mapped[str | None] = mapped_column(String(64))

    desired_status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.REQUESTED, nullable=False
    )
    observed_status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.STOPPED, nullable=False
    )
    container_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
