"""Common FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker


async def db_session() -> AsyncIterator[AsyncSession]:
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def actor_from_header(x_actor: str | None = Header(default=None)) -> str | None:
    if not x_actor:
        return None
    return x_actor.strip()[:128] or None
