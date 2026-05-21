"""Stage 4 rules engine — PHASE_4_SPEC §8 criterion 2."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.core.models.ratesheet import (
    ExtractionMetadata,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
)
from packages.ingest.rules_engine import apply_hard_rules

_TODAY = datetime(2026, 5, 21, tzinfo=UTC)


def _meta() -> ExtractionMetadata:
    return ExtractionMetadata(
        extractor_model="gemini-3.1-flash-lite",
        extracted_at=_TODAY,
        prompt_version="t1",
        cell_count=10,
    )


def _lane(**overrides: object) -> LaneRecord:
    defaults: dict[str, object] = {
        "lane_id": "L1",
        "origin_port": PortCode(code="NLRTM"),
        "destination_port": PortCode(code="USNYC"),
        "equipment_type": "40HC",
        "commodity_code": None,
        "base_rate_usd": Decimal("2100"),
        "surcharges": [],
        "transit_time_days": 20,
        "validity_start": date(2026, 1, 1),
        "validity_end": date(2026, 12, 31),
        "source_row_reference": SourceRow(sheet_name="Rates", row_number=2, cell_reference="A2:F2"),
    }
    defaults.update(overrides)
    return LaneRecord(**defaults)  # type: ignore[arg-type]


def _wrap(lane: LaneRecord) -> NormalizedRatesheet:
    return NormalizedRatesheet(
        job_id="job-1",
        prospect_id="prosp-1",
        extraction_metadata=_meta(),
        lanes=[lane],
    )


def test_golden_path_lane_passes_all_rules() -> None:
    rs, violations = apply_hard_rules(_wrap(_lane()), now=_TODAY)
    assert violations == []
    assert len(rs.lanes) == 1
    assert rs.deterministically_rejected == []


def test_r2_negative_rate_rejected() -> None:
    rs, violations = apply_hard_rules(_wrap(_lane(base_rate_usd=Decimal("-1"))), now=_TODAY)
    assert [v.rule_id for v in violations] == ["negative_base_rate"]
    assert rs.lanes == []
    assert len(rs.deterministically_rejected) == 1


def test_r3_validity_window_in_the_past_rejected() -> None:
    rs, violations = apply_hard_rules(
        _wrap(_lane(validity_start=date(2024, 1, 1), validity_end=date(2024, 6, 30))),
        now=_TODAY,
    )
    assert [v.rule_id for v in violations] == ["validity_window_in_the_past"]
    assert rs.lanes == []


def test_r4_inverted_validity_window_rejected() -> None:
    rs, violations = apply_hard_rules(
        _wrap(_lane(validity_start=date(2026, 12, 1), validity_end=date(2026, 6, 30))),
        now=_TODAY,
    )
    assert [v.rule_id for v in violations] == ["validity_window_inverted"]
    assert rs.lanes == []


def test_r5_transit_time_out_of_range_rejected() -> None:
    """R5 is defense-in-depth: Pydantic Field(le=120) already blocks construction
    via the validated path. Bypass-construct to exercise the rule engine branch
    that catches upstream serialization gaps."""
    bad = _lane()
    object.__setattr__(bad, "transit_time_days", 121)
    rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["transit_time_out_of_range"]
    assert rs.lanes == []


def test_first_violation_wins() -> None:
    """A lane that breaks multiple rules is rejected on the FIRST one only.

    R2 (negative rate) + R5 (transit-time-OOR): R1..R7 ordering means R2 fires.
    transit_time bypass-set since Pydantic blocks le=120 violations.
    """
    bad = _lane(base_rate_usd=Decimal("-1"))
    object.__setattr__(bad, "transit_time_days", 200)
    _rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["negative_base_rate"]
