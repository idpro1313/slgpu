"""Запись действий пользователя в БД, для которых нет фоновой CLI-job."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


async def record_ui_action(
    session: AsyncSession,
    *,
    action: str,
    actor: str | None = None,
    target: str | None = None,
    payload: dict[str, Any] | None = None,
    note: str | None = None,
) -> None:
    """Добавляет событие. `correlation_id` не задаётся — такие события не дублируют строки `jobs`."""

    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            target=target,
            correlation_id=None,
            payload=payload or {},
            note=note,
        )
    )
