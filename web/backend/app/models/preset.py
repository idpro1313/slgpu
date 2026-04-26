"""Preset declaration. Synchronised to/from <PRESETS_DIR>/<slug>.env (default data/presets)."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Preset(Base):
    __tablename__ = "presets"
    __table_args__ = (UniqueConstraint("name", name="uq_presets_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    model_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("models.id", ondelete="SET NULL"), nullable=True
    )
    hf_id: Mapped[str] = mapped_column(String(256), nullable=False)

    tp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gpu_mask: Mapped[str | None] = mapped_column(String(64), nullable=True)
    served_model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
