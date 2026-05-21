"""Strict-forbid round-trip tests for every new Phase 2 BaseModel.

PHASE_2_SPEC §8 criterion 8.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from packages.core.models import ingress, ratesheet
from packages.core.models.ratesheet import (
    ClassifiedFormat,
    ExtractionMetadata,
    FlaggedLane,
    JobStatus,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    RejectionRecord,
    SourceRow,
    SurchargeRecord,
)


def _valid_examples() -> dict[type[BaseModel], dict[str, object]]:
    """Return a minimal valid kwargs dict for each Phase 2 model."""
    src_row = {"sheet_name": "Rates", "row_number": 2, "cell_reference": "A2:F2"}
    surcharge = {"code": "BAF", "amount_usd": "350", "applies_per": "container"}
    port = {"code": "NLRTM"}
    lane = {
        "lane_id": "L1",
        "origin_port": port,
        "destination_port": {"code": "USNYC"},
        "equipment_type": "40HC",
        "base_rate_usd": "2100",
        "surcharges": [surcharge],
        "validity_start": "2026-01-01",
        "validity_end": "2026-06-30",
        "source_row_reference": src_row,
    }
    metadata = {
        "extractor_model": "gemini-3.1-flash-lite",
        "extracted_at": "2026-05-19T12:00:00+00:00",
        "prompt_version": "stage2.excel.v1",
        "cell_count": 25,
    }
    return {
        ingress.RatesheetIngressRequest: {
            "prospect_id": "p123",
            "prospect_name": "Acme",
            "source_format_hint": "auto",
            "requesting_user_slack_id": "U123",
            "callback_channel": "#freight",
        },
        PortCode: port,
        SurchargeRecord: surcharge,
        SourceRow: src_row,
        ExtractionMetadata: metadata,
        LaneRecord: lane,
        FlaggedLane: {"lane": lane, "reason": "low_confidence", "confidence": "0.5"},
        RejectionRecord: {
            "source_row_reference": src_row,
            "rule_id": "RULE_X",
            "rule_description": "invalid equipment",
        },
        NormalizedRatesheet: {
            "job_id": "j1",
            "prospect_id": "p123",
            "extraction_metadata": metadata,
            "lanes": [lane],
        },
        JobStatus: {
            "job_id": "j1",
            "status": "pending",
            "created_at": "2026-05-19T12:00:00+00:00",
        },
        ClassifiedFormat: {
            "detected_format": "excel",
            "confidence": 0.99,
            "reason": "xlsx_magic",
        },
    }


@pytest.mark.parametrize("model_cls,kwargs", list(_valid_examples().items()))
def test_valid_payload_accepted(model_cls: type[BaseModel], kwargs: dict[str, object]) -> None:
    """The minimal valid example for every Phase 2 model must parse."""
    instance = model_cls.model_validate(kwargs)
    assert isinstance(instance, model_cls)


@pytest.mark.parametrize("model_cls,kwargs", list(_valid_examples().items()))
def test_unknown_field_rejected(model_cls: type[BaseModel], kwargs: dict[str, object]) -> None:
    """extra='forbid' must reject an unknown field on every new BaseModel."""
    polluted = {**kwargs, "__unexpected_field__": "boom"}
    with pytest.raises(ValidationError):
        model_cls.model_validate(polluted)


def test_portcode_pattern_enforced() -> None:
    """PortCode regex rejects lowercase / wrong-length input."""
    with pytest.raises(ValidationError):
        PortCode(code="nlrtm")
    with pytest.raises(ValidationError):
        PortCode(code="NLRT")


def test_normalized_ratesheet_schema_version_locked() -> None:
    """schema_version is a Literal['onramp.v1'] and cannot be set to anything else."""
    valid = _valid_examples()[NormalizedRatesheet]
    with pytest.raises(ValidationError):
        NormalizedRatesheet.model_validate({**valid, "schema_version": "onramp.v2"})


def test_extraction_metadata_cell_count_capped() -> None:
    """cell_count ≥ 5000 is rejected by ExtractionMetadata (matches extractor cap)."""
    base = _valid_examples()[ExtractionMetadata]
    with pytest.raises(ValidationError):
        ratesheet.ExtractionMetadata.model_validate({**base, "cell_count": 5001})
