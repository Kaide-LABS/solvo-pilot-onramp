"""Async query helpers for wco_hs6_reference. Implements PHASE_3_SPEC.md §1."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import WcoHs6Reference


async def lookup_hs6(session: AsyncSession, hs6: str) -> WcoHs6Reference | None:
    """Return the WCO HS6 row for the given six-digit code, or None."""
    if len(hs6) != 6 or not hs6.isdigit():
        return None
    result = await session.execute(select(WcoHs6Reference).where(WcoHs6Reference.hs6 == hs6))
    return result.scalar_one_or_none()


async def candidates_by_heading(session: AsyncSession, heading: str) -> list[WcoHs6Reference]:
    """Return all HS6 rows whose four-digit heading matches the input."""
    if len(heading) != 4 or not heading.isdigit():
        return []
    result = await session.execute(
        select(WcoHs6Reference).where(WcoHs6Reference.heading == heading)
    )
    return list(result.scalars().all())
