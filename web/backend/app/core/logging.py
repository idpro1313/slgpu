"""Structured logging configuration following the slgpu GRACE convention.

Each log line is shaped as `[Module][fn][BLOCK] message` with optional
JSON payload to make grep and Loki queries cheap.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
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


def configure_logging(
    level: str = "INFO",
    data_dir: Path | None = None,
    *,
    log_file_enabled: bool = False,
) -> None:
    """StreamHandler + ``DbLogHandler`` (очередь → SQLite ``app_log_event``) + опциональный файл.

    Файл ``<WEB_DATA_DIR>/.slgpu/app.log`` (5 MiB×3) — только при ``WEB_LOG_FILE_ENABLED=true`` (Loki).
    UI «Логи» читает ``GET /api/v1/app-logs/events`` из БД. ``uvicorn.access`` → WARNING.
    Uvicorn после импорта снова добавляет handler'ы — вызывайте в ``startup`` с теми же аргументами.
    """
    from app.services.app_log_sink import get_db_log_handler

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(get_db_log_handler())
    root.setLevel(resolved_level)

    if data_dir is not None and log_file_enabled:
        log_sub = data_dir / ".slgpu"
        try:
            log_sub.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # noqa: BLE001
            sys.stderr.write(f"slgpu-web: could not create {log_sub}: {exc}\n")
        else:
            fpath = log_sub / "app.log"
            try:
                fh = RotatingFileHandler(
                    fpath,
                    maxBytes=5 * 1024 * 1024,
                    backupCount=3,
                    encoding="utf-8",
                )
                fh.setFormatter(_JsonFormatter())
                root.addHandler(fh)
            except OSError as exc:  # noqa: BLE001
                sys.stderr.write(f"slgpu-web: file logging disabled ({fpath}): {exc}\n")

    for logger_name in (
        "app",
        "httpx",
        "httpcore",
        "h11",
        "uvicorn",
        "uvicorn.error",
        "fastapi",
        "starlette",
    ):
        named = logging.getLogger(logger_name)
        named.handlers.clear()
        named.setLevel(resolved_level)
        named.propagate = True
    # Дубли с middleware «HTTP исход» — только WARNING+ на access.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.setLevel(logging.WARNING)
    access.propagate = True
