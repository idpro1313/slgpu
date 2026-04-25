"""Pytest fixtures shared across the slgpu-web backend tests.

The tests do not touch a real Docker daemon, a real Hugging Face cache,
or the network. We point the backend at a temporary `slgpu_root` and a
file-backed SQLite database under tmp_path so the suite is hermetic.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    fake_root = tmp_path / "slgpu"
    (fake_root / "data" / "presets").mkdir(parents=True)
    (fake_root / "main.env").write_text(
        "MODELS_DIR=" + str(tmp_path / "models") + "\n"
        "PRESETS_DIR=./data/presets\n",
        encoding="utf-8",
    )
    (fake_root / "slgpu").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    os.makedirs(tmp_path / "data", exist_ok=True)
    db_path = tmp_path / "web.db"

    monkeypatch.setenv("WEB_SLGPU_ROOT", str(fake_root))
    monkeypatch.setenv("WEB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WEB_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    from app.core.config import get_settings
    from app.db import session as db_session
    from app.services import jobs as jobs_service

    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None
    jobs_service._active_locks.clear()

    yield

    db_session._engine = None
    db_session._session_factory = None
    jobs_service._active_locks.clear()
    get_settings.cache_clear()
