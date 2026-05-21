"""Async engine + session dependency. Implements PHASE_6_5_SPEC.md §6.1.

Phase 6.5 fix for Defect 1: the prior lru-cached `get_async_engine` returned
a single AsyncEngine whose asyncpg connections were bound to whichever event
loop opened them. Under Celery, each task calls `asyncio.run(...)` which spins
up a fresh loop per invocation, so the cached engine's pool connections were
attached to a now-closed loop on the second-and-onwards task — surfacing as
`RuntimeError: got Future attached to a different loop`.

Contract:
- `make_async_engine(settings)` constructs a fresh engine. CALLER owns disposal.
- FastAPI lifespan calls `make_async_engine` once at startup and disposes once
  at shutdown, attaching the engine to `app.state.db_engine`.
- Every Postgres-touching Celery task constructs + disposes its own engine
  inside `asyncio.run`'s loop.
- `get_async_session` reads the lifespan-owned engine off `request.app.state`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from packages.core.settings import Settings, get_settings


def make_async_engine(settings: Settings | None = None) -> AsyncEngine:
    """Construct a fresh AsyncEngine bound to the configured Postgres DSN.

    NOT cached. Caller is responsible for `await engine.dispose()` at the end
    of the surrounding event-loop lifetime. The FastAPI lifespan owns its
    engine for the whole process; each Celery task owns its engine for the
    duration of `asyncio.run(...)`.
    """
    settings = settings or get_settings()
    return create_async_engine(
        settings.postgres_dsn_async,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        future=True,
    )


async def get_async_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession from the lifespan engine.

    Reads `request.app.state.db_engine` (set in `apps/api/main.py:lifespan`).
    """
    engine: AsyncEngine = request.app.state.db_engine
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
