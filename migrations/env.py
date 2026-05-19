"""Alembic env.py — async configuration. Implements PHASE_1_SPEC.md §5."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import packages so all ORM model modules are registered before
# target_metadata is read.
import packages.core.db.base as _db_base  # noqa: F401
from packages.core.db.base import Base
from packages.core.settings import get_settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.postgres_dsn_sync)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode — emit raw SQL to stdout."""
    context.configure(
        url=_settings.postgres_dsn_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Run migrations against a live connection — invoked by run_sync."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    """Online migration path against an async engine."""
    section: dict[str, Any] = config.get_section(config.config_ini_section, {}) or {}
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=_settings.postgres_dsn_async,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online_async())
