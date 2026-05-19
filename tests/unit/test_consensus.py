"""Majority-vote consensus. PHASE_3_SPEC.md §8 criterion 5."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from packages.core.models.normalization import EnsembleVote
from packages.core.models.ratesheet import (
    LaneRecord,
    PortCode,
    SourceRow,
)
from packages.ingest.consensus import majority_consensus


def _lane(*, origin: str = "NLRTM", dest: str = "USNYC", rate: str = "2100") -> LaneRecord:
    return LaneRecord(
        lane_id="L1",
        origin_port=PortCode(code=origin),
        destination_port=PortCode(code=dest),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal(rate),
        surcharges=[],
        transit_time_days=None,
        validity_start=date(2026, 1, 1),
        validity_end=date(2026, 6, 30),
        source_row_reference=SourceRow(sheet_name="Rates", row_number=2, cell_reference="A2:F2"),
    )


def _vote(idx: int, temp: float, lane: LaneRecord) -> EnsembleVote:
    return EnsembleVote(
        sample_index=idx,  # type: ignore[arg-type]
        temperature=temp,  # type: ignore[arg-type]
        lane=lane,
        raw_response_hash=f"hash{idx:04d}",
    )


def test_three_zero_agreement_yields_clean_consensus() -> None:
    """All three votes identical → clean consensus, requires_review=False."""
    base = _lane()
    votes = [_vote(0, 0.1, base), _vote(1, 0.5, base), _vote(2, 0.9, base)]
    result = majority_consensus("L1", votes)
    assert result.consensus_lane == base
    assert result.requires_review is False
    assert result.review_reason == "agreement_clean"
    assert all(c == 3 for c in result.agreement_per_field.values())


def test_two_one_majority_picks_majority() -> None:
    """2-1 majority on each field still produces a consensus lane."""
    a = _lane(origin="NLRTM")
    b = _lane(origin="DEHAM")
    votes = [_vote(0, 0.1, a), _vote(1, 0.5, a), _vote(2, 0.9, b)]
    result = majority_consensus("L1", votes)
    assert result.consensus_lane is not None
    assert result.consensus_lane.origin_port.code == "NLRTM"
    assert result.requires_review is False


def test_one_one_one_tie_yields_no_majority() -> None:
    """1-1-1 tie on any field → consensus_lane=None, no_majority."""
    a = _lane(origin="NLRTM")
    b = _lane(origin="DEHAM")
    c = _lane(origin="BEANR")
    votes = [_vote(0, 0.1, a), _vote(1, 0.5, b), _vote(2, 0.9, c)]
    result = majority_consensus("L1", votes)
    assert result.consensus_lane is None
    assert result.requires_review is True
    assert result.review_reason == "no_majority"


def test_majority_consensus_requires_at_least_one_vote() -> None:
    """Empty votes list raises ValueError."""
    with pytest.raises(ValueError):
        majority_consensus("L1", [])
