"""Reference query helpers for wco_hs6_reference. PHASE_3_SPEC §8."""

from __future__ import annotations

from typing import Any

import pytest

from packages.core.db.base import WcoHs6Reference
from packages.reference import wco_hs6 as wh


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._value if isinstance(self._value, list) else []


class _FakeSession:
    def __init__(self, value: Any) -> None:
        self._value = value

    async def execute(self, *_a: Any, **_kw: Any) -> _Result:
        return _Result(self._value)


@pytest.mark.asyncio
async def test_lookup_hs6_returns_row_on_six_digit() -> None:
    """Six-digit numeric input is forwarded to the DB and the row returned."""
    row = WcoHs6Reference(hs6="010101", chapter="01", heading="0101", description="x")
    result = await wh.lookup_hs6(_FakeSession(row), "010101")  # type: ignore[arg-type]
    assert result is row


@pytest.mark.asyncio
async def test_lookup_hs6_rejects_non_six_digit_without_db_call() -> None:
    """Non-conforming input short-circuits to None — no DB call attempted."""
    session = _FakeSession(
        WcoHs6Reference(hs6="010101", chapter="01", heading="0101", description="x")
    )
    assert await wh.lookup_hs6(session, "01010") is None  # type: ignore[arg-type]
    assert await wh.lookup_hs6(session, "abcdef") is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_candidates_by_heading_filters_invalid() -> None:
    """Non-four-digit heading returns an empty list."""
    session = _FakeSession([])
    assert await wh.candidates_by_heading(session, "010") == []  # type: ignore[arg-type]
    assert await wh.candidates_by_heading(session, "abcd") == []  # type: ignore[arg-type]
