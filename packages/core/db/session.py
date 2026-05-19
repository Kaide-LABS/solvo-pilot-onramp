"""Async engine + session dependency. Phase 1 use: boot validators only."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from packages.core.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Return a cached async engine bound to the configured Postgres DSN.

    Pool sizing kept conservative for Phase 1 (boot validators only).
    Later phases tune for worker concurrency.
    """
    settings: Settings = get_settings()
    return create_async_engine(
        settings.postgres_dsn_async,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        future=True,
    )


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession.

    Not used by any route in Phase 1; reserved for Phase 2 ingress handlers.
    """
    engine = get_async_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
