"""Единая лента «Задачи»: фоновые CLI-job и прочие действия пользователя из audit_events."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.models.audit import AuditEvent
from app.models.job import Job
from app.schemas.activity import ActivityJobItem, ActivityUiItem
from app.schemas.jobs import JobOut

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_activity(
    jobs_batch: Sequence[Job],
    audits_batch: Sequence[AuditEvent],
    *,
    limit: int,
) -> list[ActivityJobItem | ActivityUiItem]:
    rows: list[tuple[datetime, str, object]] = []
    for j in jobs_batch:
        rows.append((j.created_at, "job", j))
    for a in audits_batch:
        rows.append((a.created_at, "ui", a))
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[ActivityJobItem | ActivityUiItem] = []
    for created_at, kind, obj in rows[:limit]:
        if kind == "job" and isinstance(obj, Job):
            try:
                out.append(
                    ActivityJobItem(created_at=created_at, job=JobOut.model_validate(obj, from_attributes=True))
                )
            except Exception:  # noqa: BLE001
                logger.exception("[activity] skip bad job row id=%s", getattr(obj, "id", None))
        elif kind == "ui" and isinstance(obj, AuditEvent):
            out.append(
                ActivityUiItem(
                    type="ui",
                    created_at=created_at,
                    audit_id=obj.id,
                    action=obj.action,
                    target=obj.target,
                    actor=obj.actor,
                    note=obj.note,
                    payload=dict(obj.payload or {}),
                )
            )
    return out


@router.get("", response_model=list[ActivityJobItem | ActivityUiItem])
async def list_activity(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(db_session),
) -> list[ActivityJobItem | ActivityUiItem]:
    """CLI-операции (таблица `jobs`) + UI-действия (`audit_events` с `correlation_id IS NULL`).

    События, созданные `jobs.submit` вместе с job, имеют `correlation_id` и в ленте **не
    дублируются** — остаётся строка job (stdout/stderr).
    """
    j_q = await session.execute(select(Job).order_by(Job.id.desc()).limit(300))
    jobs_batch = list(j_q.scalars().all())

    a_q = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.correlation_id.is_(None))
        .order_by(AuditEvent.id.desc())
        .limit(300)
    )
    audits_batch = list(a_q.scalars().all())

    return _build_activity(jobs_batch, audits_batch, limit=limit)
