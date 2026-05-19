"""Conformal-prediction + rule-violation models. Implements PHASE_4_SPEC.md §3.2.

The 0.85 acceptance threshold is locked at the Literal level so env-var drift
cannot relax it. The rule_id Literal is the exhaustive PHASE 4 rule catalogue.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RuleId = Literal[
    "port_unknown_unlocode",
    "negative_base_rate",
    "validity_window_in_the_past",
    "validity_window_inverted",
    "transit_time_out_of_range",
    "equipment_type_unknown",
    "surcharge_basis_unknown",
]


class ConformalScore(BaseModel):
    """Per-lane conformal confidence in [0.0, 1.0]. Stage 4 product."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str = Field(min_length=1, max_length=64)
    confidence: Decimal = Field(ge=Decimal("0.000"), le=Decimal("1.000"))
    method: Literal["section_granular_split_conformal"]
    calibration_id: str = Field(min_length=1, max_length=64)


class ConformalCalibration(BaseModel):
    """Held-out calibration record used to derive the 0.85 acceptance threshold.

    Loaded from fixtures/conformal_calibration_v1.json at boot. The threshold
    itself is non-negotiable — pinned at the Literal level.
    """

    model_config = ConfigDict(extra="forbid")

    calibration_id: str = Field(min_length=1, max_length=64)
    sample_count: int = Field(ge=50)
    acceptance_threshold: Literal["0.85"] = "0.85"
    generated_at: str = Field(min_length=10, max_length=32)


class RuleViolation(BaseModel):
    """One Stage 4 deterministic-rule failure attached to a RejectionRecord."""

    model_config = ConfigDict(extra="forbid")

    rule_id: RuleId
    rule_description: str = Field(min_length=4, max_length=256)
