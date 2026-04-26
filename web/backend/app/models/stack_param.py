"""One row per stack or secret parameter (replaces bulk JSON in ``settings`` for cfg.stack/cfg.secrets)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StackParam(Base):
    __tablename__ = "stack_params"
    __table_args__ = (UniqueConstraint("param_key", name="uq_stack_params_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    param_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
