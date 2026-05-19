"""Async query helpers for un_locode_reference + carrier_port_aliases.

Implements PHASE_3_SPEC.md §1 (reference module). Pure-deterministic — zero
LLM calls. The port resolver in packages/ingest/port_resolver.py composes
these helpers into the resolution chain.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import CarrierPortAlias, UnLocodeReference


async def lookup_canonical_code(session: AsyncSession, code: str) -> UnLocodeReference | None:
    """Return the UN/LOCODE row for an exact code match, or None."""
    result = await session.execute(
        select(UnLocodeReference).where(UnLocodeReference.code == code.upper())
    )
    return result.scalar_one_or_none()


async def lookup_alias(session: AsyncSession, alias: str) -> CarrierPortAlias | None:
    """Return the carrier-alias row for an exact alias match, or None."""
    result = await session.execute(
        select(CarrierPortAlias).where(CarrierPortAlias.alias == alias.upper())
    )
    return result.scalar_one_or_none()


async def row_count(session: AsyncSession) -> int:
    """Return total rows in un_locode_reference. Used by tests + diagnostics."""
    result = await session.execute(select(UnLocodeReference.code))
    return len(result.scalars().all())
