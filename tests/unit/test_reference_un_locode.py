"""Reference query helpers for un_locode_reference. PHASE_3_SPEC §8."""

from __future__ import annotations

from typing import Any

import pytest

from packages.core.db.base import CarrierPortAlias, UnLocodeReference
from packages.reference import un_locode as ul


class _ScalarResult:
    """Stand-in for a SQLAlchemy Result whose scalar_one_or_none returns a value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """Minimal async session whose execute() yields canned scalar results."""

    def __init__(self, value: Any) -> None:
        self._value = value

    async def execute(self, *_args: Any, **_kw: Any) -> _ScalarResult:
        return _ScalarResult(self._value)


@pytest.mark.asyncio
async def test_lookup_canonical_code_returns_row_when_present() -> None:
    """The helper returns the seeded UnLocodeReference row."""
    row = UnLocodeReference(
        code="NLRTM",
        country_code="NL",
        place_name="Rotterdam",
        subdivision=None,
        function="12345-78-",
    )
    session = _FakeSession(row)
    result = await ul.lookup_canonical_code(session, "nlrtm")  # type: ignore[arg-type]
    assert result is row


@pytest.mark.asyncio
async def test_lookup_alias_returns_row_when_present() -> None:
    """Alias lookup returns the seeded CarrierPortAlias row."""
    row = CarrierPortAlias(alias="BSAS", canonical="ARBUE", source="fixture")
    session = _FakeSession(row)
    result = await ul.lookup_alias(session, "bsas")  # type: ignore[arg-type]
    assert result is row


@pytest.mark.asyncio
async def test_lookup_alias_returns_none_when_missing() -> None:
    """Alias miss returns None without raising."""
    session = _FakeSession(None)
    result = await ul.lookup_alias(session, "ZZZZ")  # type: ignore[arg-type]
    assert result is None
