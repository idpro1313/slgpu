"""Асинхронная запись структурированных логов в SQLite (таблица ``app_log_event``)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.app_log_event import AppLogEvent

TABLE = AppLogEvent.__table__

# GRACE [M-WEB][app_log_sink][BLOCK_APP_LOG_SINK]

_EXC_MAX = 8192
_MSG_MAX = 2000
_EXTRA_MAX = 4096
_PRE_BUFFER_MAX = 5000
_BATCH_MAX = 200
_FLUSH_SEC = 0.5

_ANCHOR_RE = re.compile(r"^(\[[^\]]+\](?:\[[^\]]+\])+)")

_SECRET_SUBSTR = ("password", "secret", "token", "authorization", "api_key", "bearer")

_reserved_for_http = frozenset(
    {"method", "path", "status", "duration_ms", "request_id", "query_hint", "msg", "args"}
)

_log_emit_errors = 0


@dataclass
class AppLogEventDTO:
    level: str
    logger_name: str
    event_kind: str
    message: str
    http_method: str | None = None
    http_path: str | None = None
    query_hint: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    module_anchor: str | None = None
    log_extra: dict[str, Any] | None = None
    exc_summary: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "logger_name": self.logger_name,
            "event_kind": self.event_kind,
            "message": self.message[:_MSG_MAX],
            "http_method": self.http_method,
            "http_path": self.http_path[:512] if self.http_path else None,
            "query_hint": self.query_hint[:256] if self.query_hint else None,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "module_anchor": self.module_anchor[:128] if self.module_anchor else None,
            "log_extra": self.log_extra,
            "exc_summary": self.exc_summary[:_EXC_MAX] if self.exc_summary else None,
            "created_at": self.created_at,
            "updated_at": self.created_at,
        }


def _truncate_exc(text: str) -> str:
    if len(text) <= _EXC_MAX:
        return text
    return text[: _EXC_MAX - 3] + "..."


def _safe_extra_from_record(record: logging.LogRecord) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED_LOG_ATTRS:
            continue
        if key in _reserved_for_http:
            continue
        lk = key.lower()
        if any(s in lk for s in _SECRET_SUBSTR):
            continue
        try:
            json.dumps(value, default=str)
            out[key] = value
        except (TypeError, ValueError):
            out[key] = repr(value)[:500]
    if not out:
        return None
    try:
        blob = json.dumps(out, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return None
    if len(blob) > _EXTRA_MAX:
        return {"_truncated": True, "_note": "extra too large; omitted"}
    return out


_RESERVED_LOG_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "msecs",
        "relativeCreated",
        "levelno",
        "levelname",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "message",
        "process",
        "processName",
        "thread",
        "threadName",
        "taskName",
    }
)


def _classify_event_kind(record: logging.LogRecord, msg: str) -> str:
    name = record.name
    level = record.levelname
    if name == "app.http":
        if "BLOCK_API_ERROR" in msg:
            return "http_error"
        return "http_request"
    if name == "app.main" or msg.startswith("[main]"):
        return "app_lifecycle"
    if name.startswith("app.") and level == "WARNING":
        return "app_warning"
    if name.startswith("app.") and level in ("ERROR", "CRITICAL"):
        return "app_error"
    if level in ("ERROR", "CRITICAL") and (
        name.startswith("uvicorn") or name.startswith("starlette") or name.startswith("fastapi")
    ):
        return "app_error"
    if name.split(".")[0] in ("httpx", "httpcore", "h11", "uvicorn", "starlette", "fastapi"):
        return "dependency"
    if name.startswith("app."):
        return "dependency"
    return "dependency"


def _module_anchor(msg: str) -> str | None:
    m = _ANCHOR_RE.match(msg.strip())
    if not m:
        return None
    s = m.group(1)
    return s[:128] if len(s) > 128 else s


def classify_record_to_dto(record: logging.LogRecord) -> AppLogEventDTO:
    msg = record.getMessage()
    if len(msg) > _MSG_MAX:
        msg = msg[: _MSG_MAX - 3] + "..."
    kind = _classify_event_kind(record, msg)
    created_at = datetime.fromtimestamp(record.created, tz=timezone.utc)
    exc_summary: str | None = None
    if record.exc_info:
        exc_summary = _truncate_exc(logging.Formatter().formatException(record.exc_info))
    anchor = _module_anchor(msg)

    http_method = getattr(record, "method", None)
    http_path = getattr(record, "path", None)
    query_hint = getattr(record, "query_hint", None)
    status = getattr(record, "status", None)
    duration_ms = getattr(record, "duration_ms", None)
    request_id = getattr(record, "request_id", None)
    correlation_id = getattr(record, "correlation_id", None)

    st: int | None = int(status) if status is not None else None
    dur: float | None = float(duration_ms) if duration_ms is not None else None

    extra = _safe_extra_from_record(record)

    return AppLogEventDTO(
        level=record.levelname,
        logger_name=record.name[:128],
        event_kind=kind,
        message=msg,
        http_method=http_method[:8] if isinstance(http_method, str) else None,
        http_path=http_path[:512] if isinstance(http_path, str) else None,
        query_hint=query_hint[:256] if isinstance(query_hint, str) else None,
        status_code=st,
        duration_ms=dur,
        request_id=request_id[:36] if isinstance(request_id, str) else None,
        correlation_id=correlation_id[:36] if isinstance(correlation_id, str) else None,
        module_anchor=anchor,
        log_extra=extra,
        exc_summary=exc_summary,
        created_at=created_at,
    )


_queue: asyncio.Queue[AppLogEventDTO] | None = None
_loop: asyncio.AbstractEventLoop | None = None
_writer_task: asyncio.Task[None] | None = None
_pre_buffer: list[AppLogEventDTO] = []


def enqueue_dto(dto: AppLogEventDTO) -> None:
    global _queue, _loop
    if _queue is not None and _loop is not None and _loop.is_running():
        try:
            _loop.call_soon_threadsafe(_queue.put_nowait, dto)
            return
        except Exception:  # noqa: BLE001
            pass
    if len(_pre_buffer) < _PRE_BUFFER_MAX:
        _pre_buffer.append(dto)


class DbLogHandler(logging.Handler):
    """Кладёт структурированные записи в очередь; БД пишет фоновый воркер."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            dto = classify_record_to_dto(record)
            enqueue_dto(dto)
        except Exception:  # noqa: BLE001
            global _log_emit_errors
            if _log_emit_errors < 3:
                sys.stderr.write("[app_log_sink] emit failed\n")
            _log_emit_errors += 1


_db_handler: DbLogHandler | None = None


def get_db_log_handler() -> DbLogHandler:
    global _db_handler
    if _db_handler is None:
        _db_handler = DbLogHandler(level=logging.NOTSET)
    return _db_handler


async def _flush_batch(engine: AsyncEngine, batch: list[AppLogEventDTO]) -> None:
    if not batch:
        return
    rows = [d.to_row() for d in batch]
    insp = insert(TABLE)
    async with engine.begin() as conn:
        for row in rows:
            await conn.execute(insp, row)


async def _writer_loop(engine: AsyncEngine) -> None:
    assert _queue is not None
    batch: list[AppLogEventDTO] = []
    while True:
        try:
            if not batch:
                try:
                    first = await asyncio.wait_for(_queue.get(), timeout=_FLUSH_SEC)
                except TimeoutError:
                    continue
                batch.append(first)
            while len(batch) < _BATCH_MAX:
                try:
                    batch.append(_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await _flush_batch(engine, batch)
            batch.clear()
        except asyncio.CancelledError:
            if batch:
                await _flush_batch(engine, batch)
            raise


async def start_writer(engine: AsyncEngine) -> None:
    """Старт после ``init_db``: очередь, слив pre-buffer, asyncio-задача."""
    global _queue, _loop, _writer_task
    _loop = asyncio.get_running_loop()
    if _queue is None:
        _queue = asyncio.Queue(maxsize=100_000)
    while _pre_buffer:
        try:
            await _queue.put(_pre_buffer.pop(0))
        except Exception:  # noqa: BLE001
            break
    if _writer_task is None or _writer_task.done():
        _writer_task = asyncio.create_task(_writer_loop(engine), name="app_log_writer")


async def stop_writer() -> None:
    """Останавливает воркер, сбрасывает остаток очереди в БД."""
    global _writer_task, _queue, _loop
    from app.db.session import get_engine

    eng = get_engine()
    if _writer_task is not None and not _writer_task.done():
        _writer_task.cancel()
        try:
            await _writer_task
        except asyncio.CancelledError:
            pass
    if _queue is not None:
        rest: list[AppLogEventDTO] = []
        while not _queue.empty():
            try:
                rest.append(_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if rest:
            await _flush_batch(eng, rest)
    _writer_task = None
    _queue = None
    _loop = None
