"""N=3 Pro ensemble orchestrator. PHASE_3_SPEC.md §8 criterion 4."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from packages.core.models.ratesheet import LaneRecord, PortCode, SourceRow
from packages.ingest import normalizer as nm


def _lane() -> LaneRecord:
    return LaneRecord(
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
        source_row_reference=SourceRow(sheet_name="Rates", row_number=2, cell_reference="A2:F2"),
    )


@pytest.mark.asyncio
async def test_ensemble_calls_pro_three_times_in_temperature_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator: exactly 3 Pro calls per lane, at temps (0.1, 0.5, 0.9) in that order."""
    seen_temps: list[float] = []
    seen_model: list[str] = []

    class _FakeResp:
        text = '{"lane_id":"L1","origin_port":{"code":"NLRTM"},"destination_port":{"code":"USNYC"},"equipment_type":"40HC","commodity_code":null,"base_rate_usd":"2100","surcharges":[],"transit_time_days":null,"validity_start":"2026-01-01","validity_end":"2026-06-30","source_row_reference":{"sheet_name":"Rates","row_number":2,"cell_reference":"A2:F2"}}'

    class _FakeModels:
        async def generate_content(self, *, model: str, contents: str, config: Any) -> _FakeResp:
            seen_temps.append(config.temperature)
            seen_model.append(model)
            return _FakeResp()

    class _FakeAio:
        models = _FakeModels()

    class _FakeClient:
        aio = _FakeAio()

    monkeypatch.setattr(nm, "get_vertex_client", lambda _settings: _FakeClient())
    consensus = await nm._ensemble_for_lane(_FakeClient(), _lane())
    assert len(consensus.votes) == 3
    assert seen_temps == [0.1, 0.5, 0.9]
    assert seen_model == [
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview",
    ]


def test_normalizer_temperatures_are_locked() -> None:
    """Static invariant: the locked temperature triple is exactly (0.1, 0.5, 0.9)."""
    assert nm._TEMPERATURES == (0.1, 0.5, 0.9)
    assert nm._MODEL_ID == "gemini-3.1-pro-preview"
