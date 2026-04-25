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
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved_level)

    # Uvicorn configures its own handlers before importing `app.main`.
    # Replacing handlers on the app/httpx/uvicorn logger roots makes this
    # function idempotent and prevents one record from being rendered by
    # multiple formatters in Docker/Portainer/Loki logs.
    for logger_name in ("app", "httpx", "uvicorn", "uvicorn.error", "uvicorn.access"):
        named_logger = logging.getLogger(logger_name)
        named_logger.handlers = [handler]
        named_logger.setLevel(resolved_level)
        named_logger.propagate = False
