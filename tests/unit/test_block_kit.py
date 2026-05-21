"""Block Kit summary — PHASE_5_SPEC §8 criterion 3 (no raw rates)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from packages.core.models.ratesheet import (
    ExtractionMetadata,
    FlaggedLane,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
)
from packages.slack.block_kit import build_summary_blocks


def _rs(with_flag: bool = True) -> NormalizedRatesheet:
    lane = LaneRecord(
        lane_id="L1",
        origin_port=PortCode(code="NLRTM"),
        destination_port=PortCode(code="USNYC"),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal("9999.99"),
        surcharges=[],
        transit_time_days=None,
        validity_start=date(2026, 1, 1),
        validity_end=date(2026, 6, 30),
        source_row_reference=SourceRow(sheet_name="r", row_number=2, cell_reference="A2"),
    )
    flagged: list[FlaggedLane] = (
        [FlaggedLane(lane=lane, reason="low_confidence", confidence=None)] if with_flag else []
    )
    return NormalizedRatesheet(
        job_id="job-1",
        prospect_id="ACME",
        extraction_metadata=ExtractionMetadata(
            extractor_model="gemini-3.1-flash-lite",
            extracted_at=datetime.now(UTC),
            prompt_version="v1",
            cell_count=1,
        ),
        lanes=[lane],
        flagged_for_review=flagged,
    )


def test_summary_contains_counts_and_signed_url() -> None:
    blocks = build_summary_blocks(
        rs=_rs(),
        signed_url="https://storage.googleapis.com/x/y?signed=1",
        expires_at_iso="2026-05-22T10:00:00Z",
    )
    rendered = json.dumps(blocks)
    assert "Validated lanes" in rendered
    assert "Flagged" in rendered
    assert "Rejected" in rendered
    assert "storage.googleapis.com" in rendered


def test_summary_omits_raw_rate_values() -> None:
    """The Anti-Replication boundary: never embed base_rate_usd in Slack output."""
    blocks = build_summary_blocks(
        rs=_rs(),
        signed_url="https://x/y",
        expires_at_iso="2026-05-22T10:00:00Z",
    )
    rendered = json.dumps(blocks)
    assert "9999" not in rendered
    assert "base_rate_usd" not in rendered
    assert "surcharge" not in rendered.lower() or "Flagged reasons" in rendered


def test_summary_caps_flagged_reasons_at_three() -> None:
    """At most three distinct flagged reasons appear in the context block."""
    lane = LaneRecord(
        lane_id="L1",
        origin_port=PortCode(code="NLRTM"),
        destination_port=PortCode(code="USNYC"),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal("1"),
        surcharges=[],
        transit_time_days=None,
        validity_start=date(2026, 1, 1),
        validity_end=date(2026, 6, 30),
        source_row_reference=SourceRow(sheet_name="r", row_number=2, cell_reference="A2"),
    )
    reasons = [
        "low_confidence",
        "no_majority",
        "ambiguous_field",
        "port_obfuscation_unresolved",
        "hard_rule_violation",
    ]
    rs = NormalizedRatesheet(
        job_id="job-1",
        prospect_id="ACME",
        extraction_metadata=ExtractionMetadata(
            extractor_model="gemini-3.1-flash-lite",
            extracted_at=datetime.now(UTC),
            prompt_version="v1",
            cell_count=1,
        ),
        lanes=[],
        flagged_for_review=[
            FlaggedLane(lane=lane, reason=r, confidence=None)
            for r in reasons  # type: ignore[arg-type]
        ],
    )
    blocks = build_summary_blocks(
        rs=rs, signed_url="https://x/y", expires_at_iso="2026-05-22T10:00:00Z"
    )
    rendered = json.dumps(blocks)
    # Only the first 3 distinct reasons.
    assert "low_confidence" in rendered
    assert "no_majority" in rendered
    assert "ambiguous_field" in rendered
    assert "hard_rule_violation" not in rendered
