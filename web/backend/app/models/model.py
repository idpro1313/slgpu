"""HF model registry."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelDownloadStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    PENDING = "pending"
    DOWNLOADING = "downloading"
    READY = "ready"
    ERROR = "error"
    PARTIAL = "partial"


class HFModel(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("hf_id", name="uq_models_hf_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hf_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    download_status: Mapped[ModelDownloadStatus] = mapped_column(
        Enum(ModelDownloadStatus), default=ModelDownloadStatus.UNKNOWN, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_pulled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
