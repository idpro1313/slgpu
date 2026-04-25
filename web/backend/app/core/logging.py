"""Structured logging configuration following the slgpu GRACE convention.

Each log line is shaped as `[Module][fn][BLOCK] message` with optional
JSON payload to make grep and Loki queries cheap.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


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
            if key in {"args", "msg", "levelname", "levelno", "name",
                       "pathname", "filename", "module", "exc_info", "exc_text",
                       "stack_info", "lineno", "funcName", "created",
                       "msecs", "relativeCreated", "thread", "threadName",
                       "processName", "process"}:
                continue
            base[key] = value
        return json.dumps(base, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
