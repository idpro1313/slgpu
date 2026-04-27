"""Чтение структурированного журнала (таблица ``app_log_event``)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.models.app_log_event import AppLogEvent
from app.schemas.app_logs import AppLogEventOut, AppLogEventsListOut

router = APIRouter()
logger = logging.getLogger(__name__)

_EVENT_KINDS = frozenset(
    {
        "http_request",
        "http_error",
        "app_lifecycle",
        "app_warning",
        "app_error",
        "dependency",
    }
)


def _parse_levels(s: str | None) -> list[str] | None:
    if not s or not s.strip():
        return None
    parts = {x.strip().upper() for x in s.split(",") if x.strip()}
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    out = [p for p in parts if p in allowed]
    return out or None


def _parse_kinds(s: str | None) -> list[str] | None:
    if not s or not s.strip():
        return None
    parts = {x.strip() for x in s.split(",") if x.strip()}
    out = [p for p in parts if p in _EVENT_KINDS]
    return out or None


@router.get("/events", response_model=AppLogEventsListOut, tags=["app-logs"])
async def list_app_log_events(
    session: AsyncSession = Depends(db_session),
    limit: int = Query(default=200, ge=1, le=1000),
    before_id: int | None = Query(
        default=None, description="Курсор: только строки с id < before_id (новые сверху)."
    ),
    since: str | None = Query(
        default=None,
        description="ISO-8601: только `created_at >= since` (UTC, если Z).",
    ),
    level: str | None = Query(
        default=None, description="Фильтр уровня: CSV, например INFO,WARNING,ERROR"
    ),
    event_kind: str | None = Query(
        default=None,
        description="Фильтр вида: CSV из http_request,app_error,…",
    ),
    path_prefix: str | None = Query(
        default=None, description="`http_path` начинается с (без query)",
    ),
    q: str | None = Query(
        default=None, description="Подстрока в `message` (LIKE, без регулярки)",
    ),
) -> AppLogEventsListOut:
    # GRACE [M-WEB][app_logs][BLOCK_APP_LOGS_EVENTS]
    qry = select(AppLogEvent)
    conds: list = []

    if before_id is not None:
        conds.append(AppLogEvent.id < before_id)
    if since:
        try:
            raw = since.strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            conds.append(AppLogEvent.created_at >= dt)
        except ValueError as exc:  # noqa: BLE001
            logger.debug("[app_logs] bad since: %s", since, exc_info=True)

    levs = _parse_levels(level)
    if levs:
        conds.append(AppLogEvent.level.in_(levs))

    kinds = _parse_kinds(event_kind)
    if kinds:
        conds.append(AppLogEvent.event_kind.in_(kinds))

    if path_prefix and path_prefix.strip():
        pfx = path_prefix.strip()
        conds.append(
            or_(
                AppLogEvent.http_path.startswith(pfx),
                AppLogEvent.http_path == pfx,
            )
        )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        conds.append(AppLogEvent.message.like(needle))

    if conds:
        qry = qry.where(and_(*conds))

    qry = qry.order_by(AppLogEvent.id.desc()).limit(limit + 1)
    res = await session.execute(qry)
    rows = list(res.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_before: int | None = None
    if has_more and rows:
        next_before = rows[-1].id
    return AppLogEventsListOut(
        items=[AppLogEventOut.model_validate(r, from_attributes=True) for r in rows],
        next_before_id=next_before,
    )
