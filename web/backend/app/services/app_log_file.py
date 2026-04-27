"""Путь к файлу логов приложения и чтение хвоста (UI «Логи»)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# GRACE [M-WEB][app_log_file][BLOCK_APP_LOG_PATH]
# Rotating: см. app.core.logging (RotatingFileHandler, max 5MB × 3).

CHUNK_BUDGET_BYTES = 1_000_000  # макс. читаем с конца при большом файле


def app_log_file_path() -> Path:
    """`WEB_DATA_DIR/.slgpu/app.log` (ротация: app.log.1, …)."""
    s = get_settings()
    return s.data_dir / ".slgpu" / "app.log"


def read_app_log_tail(
    max_lines: int = 500,
) -> tuple[list[str], int | None, bool, str | None]:
    """Сырой JSON по строке (как в stdout). max_lines: 1..20_000.

    Возвращает: (строки, size_bytes|None, truncated, error_message|None)
    """
    if max_lines < 1:
        max_lines = 1
    if max_lines > 20_000:
        max_lines = 20_000

    path = app_log_file_path()
    if not path.is_file():
        return [], None, False, None

    try:
        st = path.stat()
    except OSError as exc:  # noqa: BLE001
        logger.warning("[app_log_file][read_app_log_tail] stat: %s", exc)
        return [], None, False, str(exc)

    size = st.st_size
    try:
        raw: bytes
        truncated = size > CHUNK_BUDGET_BYTES
        with path.open("rb") as f:
            if not truncated:
                raw = f.read()
            else:
                f.seek(max(0, size - CHUNK_BUDGET_BYTES))
                raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        if truncated and not text.startswith("{"):
            # отрезали середину строки
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return lines, size, truncated, None
    except OSError as exc:  # noqa: BLE001
        logger.exception("[app_log_file][read_app_log_tail] read")
        return [], size, False, str(exc)
