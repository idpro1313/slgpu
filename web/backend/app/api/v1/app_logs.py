"""Чтение хвоста JSON-лога приложения (страница «Логи»)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.schemas.app_logs import AppLogsOut
from app.services.app_log_file import app_log_file_path, read_app_log_tail

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/tail", response_model=AppLogsOut, tags=["app-logs"])
async def get_app_log_tail(
    tail: int = Query(
        default=500,
        ge=1,
        le=20_000,
        description="Максимальное число последних непустых строк JSON.",
    ),
) -> AppLogsOut:
    # GRACE [M-WEB][app_logs][BLOCK_APP_LOGS_TAIL]
    lines, size, truncated, err = read_app_log_tail(max_lines=tail)
    p = app_log_file_path()
    if err:
        logger.warning("[app_logs][get_app_log_tail] %s", err)
    return AppLogsOut(
        path_hint=str(p),
        lines=lines,
        file_size_bytes=size,
        truncated_scan=truncated,
        read_error=err,
    )
