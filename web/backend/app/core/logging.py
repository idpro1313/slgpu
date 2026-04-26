"""Structured logging configuration following the slgpu GRACE convention.

Each log line is shaped as `[Module][fn][BLOCK] message` with optional
JSON payload to make grep and Loki queries cheap.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


_RESERVED_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS:
                continue
            base[key] = value
        return json.dumps(base, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Один StreamHandler на **root**: одна строка JSON на LogRecord.

    Раньше тот же handler вешали на ``httpx``/``app`` и на root — при ``propagate``
    у промежуточных логгеров запись могла обрабатываться несколько раз, что давало
    ``INFO INFO …`` в Docker/Loki. Uvicorn после импорта приложения снова добавляет
    свои handler'ы — вызывайте эту функцию повторно из ``startup`` (см. ``main``).
    """

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    for logger_name in (
        "app",
        "httpx",
        "httpcore",
        "h11",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "starlette",
    ):
        named = logging.getLogger(logger_name)
        named.handlers.clear()
        named.setLevel(resolved_level)
        named.propagate = True
