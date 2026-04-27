"""Разбор DSN SQLite для sync_merged_flat / _connect_ro (абсолютный путь в контейнере)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.stack_config import sqlite_path_from_database_url


def test_sqlite_url_four_slashes_unix_absolute() -> None:
    """Как в compose по умолчанию: ``sqlite+aiosqlite:////data/slgpu-web.db`` → ``/data/...``."""
    p = sqlite_path_from_database_url("sqlite+aiosqlite:////data/slgpu-web.db")
    assert p is not None
    assert p == Path("/data/slgpu-web.db")


def test_sqlite_url_file_in_tmp(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    db.write_bytes(b"")
    u = f"sqlite+aiosqlite:///{db.as_posix()}"
    p = sqlite_path_from_database_url(u)
    assert p is not None
    assert p.resolve() == db.resolve()


def test_in_memory_not_a_path() -> None:
    assert sqlite_path_from_database_url("sqlite+aiosqlite:///:memory:") is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@h/db",
    ],
)
def test_non_sqlite(url: str) -> None:
    assert sqlite_path_from_database_url(url) is None
