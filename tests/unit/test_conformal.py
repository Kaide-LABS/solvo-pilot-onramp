"""Conformal-prediction threshold semantics. PHASE_4_SPEC §8 criterion 3."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from packages.core.models.conformal import ConformalCalibration, ConformalScore
from packages.core.models.normalization import EnsembleVote
from packages.core.models.ratesheet import LaneRecord, PortCode, SourceRow
from packages.ingest.conformal import (
    ACCEPTANCE_THRESHOLD,
    accepts,
    compute_conformal_score,
)


def _calibration() -> ConformalCalibration:
    return ConformalCalibration(
        calibration_id="cal-1", sample_count=64, generated_at="2026-05-21T09:00:00Z"
    )


def _lane(rate: str = "2100") -> LaneRecord:
    return LaneRecord(
        lane_id="L1",
        origin_port=PortCode(code="NLRTM"),
        destination_port=PortCode(code="USNYC"),
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
        temperature=temp,
        lane=lane,
        raw_response_hash=f"hash{idx:04d}",
    )


def test_threshold_is_pinned_at_0_85() -> None:
    """The Pydantic Literal pins acceptance_threshold to the string "0.85"."""
    assert ACCEPTANCE_THRESHOLD == Decimal("0.85")
    cal = _calibration()
    assert cal.acceptance_threshold == "0.85"


def test_three_zero_agreement_yields_confidence_one() -> None:
    """All three votes identical → confidence == 1.0, passes the threshold."""
    base = _lane()
    votes = [_vote(0, 0.1, base), _vote(1, 0.5, base), _vote(2, 0.9, base)]
    score = compute_conformal_score("L1", votes, _calibration())
    assert score.confidence == Decimal("1.000")
    assert accepts(score) is True


def test_score_under_threshold_is_rejected() -> None:
    """A constructed low-agreement score is rejected by accepts()."""
    score = ConformalScore(
        lane_id="L1",
        confidence=Decimal("0.840"),
        method="section_granular_split_conformal",
        calibration_id="cal-1",
    )
    assert accepts(score) is False


def test_score_at_threshold_passes() -> None:
    """Exactly 0.85 passes (acceptance threshold is inclusive)."""
    score = ConformalScore(
        lane_id="L1",
        confidence=Decimal("0.850"),
        method="section_granular_split_conformal",
        calibration_id="cal-1",
    )
    assert accepts(score) is True
