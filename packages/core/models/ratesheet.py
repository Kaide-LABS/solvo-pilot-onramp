"""Ratesheet domain models. Implements PHASE_2_SPEC.md §3.2.

Mirrors Solvo_Master_PRD.md §3.3 verbatim. Every BaseModel declares
model_config = ConfigDict(extra="forbid") on its own line — strict-forbid
is the load-bearing white-box anchor (ULTIMATE_PRD §3 hard invariant).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceFormatHint = Literal["excel", "csv", "edifact", "email", "auto"]
DetectedFormat = Literal["excel", "csv", "edifact", "email", "uncertain"]

EquipmentType = Literal["20GP", "40GP", "40HC", "20RF", "40RF", "OOG", "BULK"]

JobStatusLiteral = Literal[
    "pending",
    "extracting",
    "normalizing",
    "validating",
    "completed",
    "failed",
]

FlagReason = Literal[
    "low_confidence",
    "no_majority",
    "ambiguous_field",
    "port_obfuscation_unresolved",
]
SurchargeBasis = Literal["container", "shipment", "bl", "teu"]


class PortCode(BaseModel):
    """UN/LOCODE-shaped port identifier. Phase 2 validates SHAPE only.

    Runtime lookup against the un_locode_reference table is Phase 3 (the
    deterministic anchor §3.5 #2). Phase 2 accepts anything matching the
    canonical regex; non-UN/LOCODE carrier-internal codes (e.g. "BSAS")
    flow through as-is and are resolved in normalization later.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$", min_length=5, max_length=5)


class SurchargeRecord(BaseModel):
    """Single surcharge line attached to a LaneRecord."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=16)
    amount_usd: Decimal
    applies_per: SurchargeBasis


class SourceRow(BaseModel):
    """Pointer back to the originating spreadsheet location."""

    model_config = ConfigDict(extra="forbid")

    sheet_name: str = Field(min_length=1, max_length=64)
    row_number: int = Field(ge=1)
    cell_reference: str = Field(min_length=2, max_length=32)


class ExtractionMetadata(BaseModel):
    """Per-job extraction provenance — which model, which prompt, when."""

    model_config = ConfigDict(extra="forbid")

    extractor_model: Literal["gemini-3-flash-preview"]
    extracted_at: datetime
    prompt_version: str = Field(min_length=1, max_length=32)
    cell_count: int = Field(ge=0, le=5_000)


class LaneRecord(BaseModel):
    """Single lane row produced by the extractor. Mirrors Master PRD §3.3."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str = Field(min_length=1, max_length=64)
    origin_port: PortCode
    destination_port: PortCode
    equipment_type: EquipmentType
    commodity_code: str | None = Field(default=None, max_length=16)
    base_rate_usd: Decimal
    surcharges: list[SurchargeRecord] = Field(default_factory=list)
    transit_time_days: int | None = Field(default=None, ge=1, le=120)
    validity_start: date
    validity_end: date
    source_row_reference: SourceRow


class FlaggedLane(BaseModel):
    """Lane diverted to human review.

    Phase 2 emits FlaggedLane with confidence=None; Phase 4 populates
    confidence after the conformal calibration runs.
    """

    model_config = ConfigDict(extra="forbid")

    lane: LaneRecord
    reason: FlagReason
    confidence: Decimal | None = None


class RejectionRecord(BaseModel):
    """Hard-rejected row with deterministic rule citation."""

    model_config = ConfigDict(extra="forbid")

    source_row_reference: SourceRow
    rule_id: str = Field(min_length=1, max_length=64)
    rule_description: str = Field(min_length=1, max_length=256)


class NormalizedRatesheet(BaseModel):
    """Final pipeline output. Phase 2 populates the extraction half only."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    prospect_id: str = Field(min_length=3, max_length=64)
    extraction_metadata: ExtractionMetadata
    lanes: list[LaneRecord]
    conformal_scores: dict[str, float] = Field(default_factory=dict)
    flagged_for_review: list[FlaggedLane] = Field(default_factory=list)
    deterministically_rejected: list[RejectionRecord] = Field(default_factory=list)
    schema_version: Literal["onramp.v1"] = "onramp.v1"


class JobStatus(BaseModel):
    """Status response surface for /v1/jobs/{id}/status."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatusLiteral
    created_at: datetime
    completed_at: datetime | None = None
    lane_count: int | None = None


class ClassifiedFormat(BaseModel):
    """Result returned by Stage 1 classifier (§6.1)."""

    model_config = ConfigDict(extra="forbid")

    detected_format: DetectedFormat
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=256)
