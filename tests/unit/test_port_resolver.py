"""Port-code resolution paths. PHASE_3_SPEC.md §8 criterion 6."""

from __future__ import annotations

from typing import Any

import pytest

from packages.core.db.base import CarrierPortAlias, UnLocodeReference
from packages.ingest import port_resolver as pr


class _FakeSession:
    """Minimal AsyncSession stand-in for unit tests."""


@pytest.mark.asyncio
async def test_direct_unlocode_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical UN/LOCODE present in the table → direct hit."""

    async def _lookup(_session: Any, code: str) -> UnLocodeReference | None:
        if code == "NLRTM":
            return UnLocodeReference(
                code="NLRTM",
                country_code="NL",
                place_name="Rotterdam",
                subdivision=None,
                function="12345-78-",
            )
        return None

    async def _alias(_session: Any, _alias: str) -> CarrierPortAlias | None:
        return None

    monkeypatch.setattr(pr, "lookup_canonical_code", _lookup)
    monkeypatch.setattr(pr, "lookup_alias", _alias)
    result = await pr.resolve_port_code("NLRTM", _FakeSession())  # type: ignore[arg-type]
    assert result.resolution_method == "direct_unlocode"
    assert result.canonical is not None
    assert result.canonical.code == "NLRTM"


@pytest.mark.asyncio
async def test_carrier_alias_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Carrier-internal alias resolves to the canonical code."""

    async def _lookup(_session: Any, _code: str) -> None:
        return None

    async def _alias(_session: Any, alias: str) -> CarrierPortAlias | None:
        if alias == "BSAS":
            return CarrierPortAlias(alias="BSAS", canonical="ARBUE", source="fixture")
        return None

    monkeypatch.setattr(pr, "lookup_canonical_code", _lookup)
    monkeypatch.setattr(pr, "lookup_alias", _alias)
    result = await pr.resolve_port_code("BSAS", _FakeSession())  # type: ignore[arg-type]
    assert result.resolution_method == "carrier_alias_table"
    assert result.canonical is not None
    assert result.canonical.code == "ARBUE"


@pytest.mark.asyncio
async def test_iata_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three-letter IATA code falls back to the colocated UN/LOCODE."""
    call_log: list[str] = []

    async def _lookup(_session: Any, code: str) -> UnLocodeReference | None:
        call_log.append(code)
        if code == "USNYC":
            return UnLocodeReference(
                code="USNYC",
                country_code="US",
                place_name="New York",
                subdivision="NY",
                function="12345-78-",
            )
        return None

    async def _alias(_session: Any, _alias: str) -> CarrierPortAlias | None:
        return None

    monkeypatch.setattr(pr, "lookup_canonical_code", _lookup)
    monkeypatch.setattr(pr, "lookup_alias", _alias)
    result = await pr.resolve_port_code("JFK", _FakeSession())  # type: ignore[arg-type]
    assert result.resolution_method == "iata_fallback"
    assert result.canonical is not None
    assert result.canonical.code == "USNYC"


@pytest.mark.asyncio
async def test_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown alias resolves to unresolved (canonical=None)."""

    async def _lookup(_session: Any, _code: str) -> None:
        return None

    async def _alias(_session: Any, _alias: str) -> None:
        return None

    monkeypatch.setattr(pr, "lookup_canonical_code", _lookup)
    monkeypatch.setattr(pr, "lookup_alias", _alias)
    result = await pr.resolve_port_code("ZZZ", _FakeSession())  # type: ignore[arg-type]
    assert result.resolution_method == "unresolved"
    assert result.canonical is None
