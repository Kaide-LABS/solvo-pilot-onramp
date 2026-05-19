"""Port-code resolution. Implements PHASE_3_SPEC.md §6.3.

Pure deterministic logic. ZERO LLM calls. Resolution order:
  1. Direct UN/LOCODE shape + canonical-table hit.
  2. Carrier alias table hit.
  3. IATA three-letter fallback against the known mapping table.
  4. Unresolved → flagged for human review.

Per ULTIMATE_PRD §3.5 #2, the deterministic-anchor invariant requires the
LLM to never guess port codes.
"""

from __future__ import annotations

import re
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.models.normalization import ResolvedPortCode
from packages.core.models.ratesheet import PortCode
from packages.reference.un_locode import lookup_alias, lookup_canonical_code

_UNLOCODE_RE: Final = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")

# Minimal IATA → UN/LOCODE fallback covering the demo fixture surface.
# Phase 4 may expand this from a vendored IATA table; Phase 3 keeps it small
# and reviewer-auditable in source.
_IATA_FALLBACK: Final[dict[str, str]] = {
    "JFK": "USNYC",
    "LAX": "USLAX",
    "LHR": "GBLON",
    "FRA": "DEFRA",
    "AMS": "NLAMS",
    "HKG": "HKHKG",
    "SHA": "CNSHA",
    "SIN": "SGSIN",
}


async def resolve_port_code(raw: str, session: AsyncSession) -> ResolvedPortCode:
    """Resolve a raw port string to a canonical UN/LOCODE.

    Returns ResolvedPortCode with resolution_method describing which branch
    succeeded. When no branch succeeds, canonical is None and the caller is
    responsible for flagging the lane with reason='port_obfuscation_unresolved'.
    """
    candidate = raw.strip().upper()

    if _UNLOCODE_RE.match(candidate):
        row = await lookup_canonical_code(session, candidate)
        if row is not None:
            return ResolvedPortCode(
                canonical=PortCode(code=row.code),
                source_alias=raw,
                resolution_method="direct_unlocode",
            )

    alias_row = await lookup_alias(session, candidate)
    if alias_row is not None:
        return ResolvedPortCode(
            canonical=PortCode(code=alias_row.canonical),
            source_alias=raw,
            resolution_method="carrier_alias_table",
        )

    if len(candidate) == 3 and candidate in _IATA_FALLBACK:
        canonical_code = _IATA_FALLBACK[candidate]
        canonical_row = await lookup_canonical_code(session, canonical_code)
        if canonical_row is not None:
            return ResolvedPortCode(
                canonical=PortCode(code=canonical_row.code),
                source_alias=raw,
                resolution_method="iata_fallback",
            )

    return ResolvedPortCode(
        canonical=None,
        source_alias=raw,
        resolution_method="unresolved",
    )
