"""Clarification phrasing node — PHASE_4_SPEC §8 criterion 5."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from packages.core.models.ratesheet import (
    FlaggedLane,
    LaneRecord,
    PortCode,
    SourceRow,
)
from packages.ingest import clarification as cl


def _flagged(reason: str = "no_majority") -> FlaggedLane:
    return FlaggedLane(
        lane=LaneRecord(
            lane_id="L1",
            origin_port=PortCode(code="NLRTM"),
            destination_port=PortCode(code="USNYC"),
            equipment_type="40HC",
            commodity_code=None,
            base_rate_usd=Decimal("2100"),
            surcharges=[],
            transit_time_days=None,
            validity_start=date(2026, 1, 1),
            validity_end=date(2026, 6, 30),
            source_row_reference=SourceRow(
                sheet_name="Rates", row_number=2, cell_reference="A2:F2"
            ),
        ),
        reason=reason,  # type: ignore[arg-type]
        confidence=None,
    )


@pytest.mark.asyncio
async def test_numeric_leak_replaced_with_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pro returns a numeric sentence → post-processor replaces with fallback."""

    class _Resp:
        text = "Ask the prospect to confirm a $1500 surcharge."

    class _Models:
        async def generate_content(self, **_kw: Any) -> _Resp:
            return _Resp()

    class _Aio:
        models = _Models()

    class _Client:
        aio = _Aio()

    monkeypatch.setattr(cl, "get_vertex_client", lambda _s: _Client())
    from packages.core.settings import get_settings

    out = await cl.draft_clarification(_flagged(), get_settings())
    assert "1500" not in out
    assert out == cl._FALLBACK_PROMPT


@pytest.mark.asyncio
async def test_clean_sentence_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pro returns a digit-free sentence → preserved verbatim."""

    class _Resp:
        text = "Ask the prospect which port code applies to the origin lane."

    class _Models:
        async def generate_content(self, **_kw: Any) -> _Resp:
            return _Resp()

    class _Aio:
        models = _Models()

    class _Client:
        aio = _Aio()

    monkeypatch.setattr(cl, "get_vertex_client", lambda _s: _Client())
    from packages.core.settings import get_settings

    out = await cl.draft_clarification(_flagged(), get_settings())
    assert out == "Ask the prospect which port code applies to the origin lane."


@pytest.mark.asyncio
async def test_pro_failure_returns_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any Pro exception → fallback prompt."""

    class _Models:
        async def generate_content(self, **_kw: Any) -> Any:
            raise RuntimeError("Vertex unavailable")

    class _Aio:
        models = _Models()

    class _Client:
        aio = _Aio()

    monkeypatch.setattr(cl, "get_vertex_client", lambda _s: _Client())
    from packages.core.settings import get_settings

    out = await cl.draft_clarification(_flagged(), get_settings())
    assert out == cl._FALLBACK_PROMPT
