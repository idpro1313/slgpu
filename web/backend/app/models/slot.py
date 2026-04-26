"""Inference slot: one vLLM/SGLang instance with dedicated GPUs and port."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.run import RunStatus


class EngineSlot(Base):
    """Desired/observed state of a single inference process (web-managed docker-py)."""

    __tablename__ = "engine_slots"
    __table_args__ = (UniqueConstraint("slot_key", name="uq_engine_slots_slot_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    preset_name: Mapped[str | None] = mapped_column(String(128))
    hf_id: Mapped[str | None] = mapped_column(String(256))
    tp: Mapped[int | None] = mapped_column(Integer)
    gpu_indices: Mapped[str | None] = mapped_column(
        String(64)
    )  # CSV, e.g. "0,1,2,3" — physical GPU indices on host
    host_api_port: Mapped[int | None] = mapped_column(Integer)
    internal_api_port: Mapped[int | None] = mapped_column(Integer)  # 8111 vLLM, 8222 SGLang

    container_id: Mapped[str | None] = mapped_column(String(80))
    container_name: Mapped[str | None] = mapped_column(String(128))

    desired_status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.REQUESTED, nullable=False
    )
    observed_status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.STOPPED, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
