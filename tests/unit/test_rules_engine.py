"""Stage 4 rules engine — PHASE_4_SPEC §8 criterion 2 + PHASE_6_9_SPEC §6.3."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.core.models.ratesheet import (
    ExtractionMetadata,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
    SurchargeRecord,
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


def test_r1_origin_port_shape_violation_rejected() -> None:
    """R1: defense-in-depth — PortCode normally enforces the regex.

    Bypass-construct a PortCode with a shape-violating code to exercise the
    rules-engine branch (Phase 6.9 §6.3).
    """
    bad_origin = PortCode.model_construct(code="zz")
    bad_lane = _lane()
    object.__setattr__(bad_lane, "origin_port", bad_origin)
    rs, violations = apply_hard_rules(_wrap(bad_lane), now=_TODAY)
    assert [v.rule_id for v in violations] == ["port_unknown_unlocode"]
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert rej.rule_id == "port_unknown_unlocode"
    assert "zz" in rej.rule_description
    assert "UN/LOCODE" in rej.rule_description


def test_r1_destination_port_shape_violation_rejected() -> None:
    """R1 also covers destination port via the second branch (Phase 6.9 §6.2)."""
    bad_dest = PortCode.model_construct(code="X1")
    bad_lane = _lane()
    object.__setattr__(bad_lane, "destination_port", bad_dest)
    rs, violations = apply_hard_rules(_wrap(bad_lane), now=_TODAY)
    assert [v.rule_id for v in violations] == ["port_unknown_unlocode"]
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "destination port" in rej.rule_description
    assert "X1" in rej.rule_description


def test_r2_negative_rate_rejected() -> None:
    rs, violations = apply_hard_rules(_wrap(_lane(base_rate_usd=Decimal("-1"))), now=_TODAY)
    assert [v.rule_id for v in violations] == ["negative_base_rate"]
    assert rs.lanes == []
    assert len(rs.deterministically_rejected) == 1
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "-1" in rej.rule_description


def test_r3_validity_window_in_the_past_rejected() -> None:
    rs, violations = apply_hard_rules(
        _wrap(_lane(validity_start=date(2024, 1, 1), validity_end=date(2024, 6, 30))),
        now=_TODAY,
    )
    assert [v.rule_id for v in violations] == ["validity_window_in_the_past"]
    assert rs.lanes == []
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "2024-06-30" in rej.rule_description


def test_r4_inverted_validity_window_rejected() -> None:
    rs, violations = apply_hard_rules(
        _wrap(_lane(validity_start=date(2026, 12, 1), validity_end=date(2026, 6, 30))),
        now=_TODAY,
    )
    assert [v.rule_id for v in violations] == ["validity_window_inverted"]
    assert rs.lanes == []
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "2026-12-01" in rej.rule_description
    assert "2026-06-30" in rej.rule_description


def test_r5_transit_time_out_of_range_rejected() -> None:
    """R5 is defense-in-depth: Pydantic Field(le=120) already blocks construction
    via the validated path. Bypass-construct to exercise the rule engine branch
    that catches upstream serialization gaps."""
    bad = _lane()
    object.__setattr__(bad, "transit_time_days", 121)
    rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["transit_time_out_of_range"]
    assert rs.lanes == []
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "121" in rej.rule_description


def test_r6_equipment_type_unknown_rejected() -> None:
    """R6: defense-in-depth — EquipmentType Literal normally blocks bad values.

    Bypass-set via object.__setattr__ to exercise the rules-engine branch.
    """
    bad = _lane()
    object.__setattr__(bad, "equipment_type", "BOGUS_RIG")
    rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["equipment_type_unknown"]
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "BOGUS_RIG" in rej.rule_description


def test_r7_surcharge_basis_unknown_rejected() -> None:
    """R7: defense-in-depth — SurchargeBasis Literal normally blocks bad values."""
    bad_surcharge = SurchargeRecord.model_construct(
        code="BAF", amount_usd=Decimal("50.00"), applies_per="WEEK"
    )
    bad = _lane()
    object.__setattr__(bad, "surcharges", [bad_surcharge])
    rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["surcharge_basis_unknown"]
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "L1"
    assert "BAF" in rej.rule_description
    assert "WEEK" in rej.rule_description


def test_first_violation_wins() -> None:
    """A lane that breaks multiple rules is rejected on the FIRST one only.

    R2 (negative rate) + R5 (transit-time-OOR): R1..R7 ordering means R2 fires.
    transit_time bypass-set since Pydantic blocks le=120 violations.
    """
    bad = _lane(base_rate_usd=Decimal("-1"))
    object.__setattr__(bad, "transit_time_days", 200)
    _rs, violations = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert [v.rule_id for v in violations] == ["negative_base_rate"]


def test_rejection_record_includes_lane_id_provenance() -> None:
    """Phase 6.9 §3 + §8 #2: every RejectionRecord carries lane_id."""
    bad = _lane(lane_id="LANE_ABC_42", base_rate_usd=Decimal("-1"))
    rs, _ = apply_hard_rules(_wrap(bad), now=_TODAY)
    assert len(rs.deterministically_rejected) == 1
    rej = rs.deterministically_rejected[0]
    assert rej.lane_id == "LANE_ABC_42"
    assert rej.source_row_reference.sheet_name == "Rates"
