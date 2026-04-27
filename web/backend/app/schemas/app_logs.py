"""Схемы API журнала приложения (файл JSON-логов)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppLogsOut(BaseModel):
    """Хвост файла `WEB_DATA_DIR/.slgpu/app.log`."""

    path_hint: str = Field(description="Семантический путь для UI (каталог data).")
    lines: list[str] = Field(default_factory=list, description="Строки JSON, как в логе.")
    file_size_bytes: int | None = None
    truncated_scan: bool = Field(
        default=False,
        description="Файл большой: прочитан только конец; первые строки срезаны по байтам.",
    )
    read_error: str | None = None
