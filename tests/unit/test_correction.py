"""Conditional Pro correction — PHASE_4_SPEC §8 criterion 4."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from packages.core.models.normalization import ConsensusResult, EnsembleVote
from packages.core.models.ratesheet import LaneRecord, PortCode, SourceRow
from packages.ingest import correction as corr


def _lane(origin: str = "NLRTM") -> LaneRecord:
    return LaneRecord(
        lane_id="L1",
        origin_port=PortCode(code=origin),
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


def _vote(idx: int, temp: float, lane: LaneRecord) -> EnsembleVote:
    return EnsembleVote(
        sample_index=idx,  # type: ignore[arg-type]
        temperature=temp,
        lane=lane,
        raw_response_hash=f"hash{idx:04d}",
    )


@pytest.mark.asyncio
async def test_correction_skipped_when_consensus_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 4 invariant: correction never runs when prior consensus was clean."""
    called = False

    async def _trap(*_args: Any, **_kw: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("correction must not be called when consensus is clean")

    monkeypatch.setattr(corr, "_one_correction_call", _trap)
    clean = ConsensusResult(
        lane_id="L1",
        consensus_lane=_lane(),
        votes=[_vote(0, 0.1, _lane()), _vote(1, 0.5, _lane()), _vote(2, 0.9, _lane())],
        agreement_per_field={"origin_port": 3},
        requires_review=False,
        review_reason="agreement_clean",
    )
    from packages.core.settings import get_settings

    result = await corr.conditional_correction(clean, get_settings())
    assert result is clean
    assert called is False


@pytest.mark.asyncio
async def test_correction_runs_two_calls_at_endpoint_temps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Correction runs exactly two calls at temps (0.0, 1.0) on disagreement."""
    seen_temps: list[float] = []

    async def _fake_call(
        _client: Any, lane: LaneRecord, idx: Any, temperature: float
    ) -> EnsembleVote:
        seen_temps.append(temperature)
        return _vote(int(idx), temperature, lane)

    monkeypatch.setattr(corr, "_one_correction_call", _fake_call)

    class _FakeClient:
        pass

    monkeypatch.setattr(corr, "get_vertex_client", lambda _s: _FakeClient())

    disagree = ConsensusResult(
        lane_id="L1",
        consensus_lane=None,
        votes=[
            _vote(0, 0.1, _lane(origin="NLRTM")),
            _vote(1, 0.5, _lane(origin="DEHAM")),
            _vote(2, 0.9, _lane(origin="BEANR")),
        ],
        agreement_per_field={},
        requires_review=True,
        review_reason="no_majority",
    )
    from packages.core.settings import get_settings

    result = await corr.conditional_correction(disagree, get_settings())
    assert sorted(seen_temps) == [0.0, 1.0]
    assert len(result.votes) == 5
