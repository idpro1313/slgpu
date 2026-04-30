"""Async SQLAlchemy session factory and lifecycle helpers.

The engine and sessionmaker are constructed lazily so that tests can
override `WEB_DATABASE_URL` from a fixture before the very first call
into the database layer. Production code paths only ever ask for a
session, so the laziness is invisible at runtime.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.url import make_url

from app.core.config import get_settings
from app.db.base import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """Create parent directory for a file-based SQLite URL if missing.

    (Does not fix permission errors on a root-owned bind mount; see
    `web/docker-entrypoint.sh`.)
    """
    from sqlalchemy.engine.url import make_url

    try:
        u = make_url(database_url)
    except Exception:  # noqa: BLE001 - best-effort only
        return
    if "sqlite" not in u.drivername:
        return
    db = (u.database or "").strip()
    if not db or db == ":memory:":
        return
    path = Path(db)
    if not path.is_absolute():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning(
            "could not create parent directory for SQLite: %s",
            path.parent,
            exc_info=True,
        )


def _sqlite_connect_args(database_url: str) -> dict | None:
    """Busy timeout so concurrent writes (request + jobs + DbLogHandler) retry instead of OperationalError."""

    try:
        u = make_url(database_url)
    except Exception:  # noqa: BLE001
        return None
    if "sqlite" not in (u.drivername or ""):
        return None
    return {"timeout": 30.0}


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _ensure_sqlite_parent_dir(settings.database_url)
        connect_args = _sqlite_connect_args(settings.database_url)
        kw: dict = {
            "future": True,
            "echo": False,
            "pool_pre_ping": True,
        }
        if connect_args is not None:
            kw["connect_args"] = connect_args
        _engine = create_async_engine(settings.database_url, **kw)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def reset_engine() -> None:
    """Tear down the cached engine. Used by tests after env changes."""

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def _sqlite_drop_legacy_preset_engine_column(connection: Connection) -> None:
    """Remove `presets.engine` if present (schema before 2.13.26)."""

    if connection.engine.dialect.name != "sqlite":
        return
    rows = connection.execute(text("PRAGMA table_info('presets')")).fetchall()
    if not any(r[1] == "engine" for r in rows):
        return
    try:
        connection.execute(text("ALTER TABLE presets DROP COLUMN engine"))
    except Exception as exc:  # noqa: BLE001 - best-effort; older SQLite
        logger.warning("Could not drop legacy presets.engine column: %s", exc)


def _sqlite_drop_runs_table(connection: Connection) -> None:
    """Remove legacy ``runs`` table (EngineRun) removed in web 4.0.0."""

    if connection.engine.dialect.name != "sqlite":
        return
    tables = connection.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    ).fetchall()
    if not tables:
        return
    try:
        connection.execute(text("DROP TABLE runs"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not drop legacy runs table: %s", exc)


async def init_db() -> None:
    """Create tables on first run.

    Schema is applied via ``create_all`` and SQLite PRAGMA cleanups; the
    single-container slgpu-web image does not ship Alembic revision history.
    """

    from app.models import (  # noqa: F401  - register mappers
        app_log_event,
        audit,
        job,
        log_report,
        model,
        preset,
        service,
        setting,
        slot,
        stack_param,
    )
    from app.services.stack_config import (
        ensure_default_settings,
        ensure_secret_flags_only,
        log_missing_canonical_keys,
        migrate_legacy_json_to_rows,
    )

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sqlite_drop_legacy_preset_engine_column)
        await conn.run_sync(_sqlite_drop_runs_table)
        if conn.engine.dialect.name == "sqlite":

            def _wal(c: Connection) -> None:  # noqa: ANN001
                c.execute(text("PRAGMA journal_mode=WAL"))

            try:
                await conn.run_sync(_wal)
            except Exception:  # noqa: BLE001
                logger.debug("WAL pragma skipped", exc_info=True)

    async with session_scope() as session:
        await migrate_legacy_json_to_rows(session)
        await ensure_default_settings(session)
        await ensure_secret_flags_only(session)
        await log_missing_canonical_keys(session)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Backwards-compatible aliases used by the older API surface.
def __getattr__(name: str):
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_sessionmaker()
    raise AttributeError(name)
