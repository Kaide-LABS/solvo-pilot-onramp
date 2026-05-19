"""Stage 4 deterministic rules engine. Implements PHASE_4_SPEC.md §6.1.

ZERO LLM CALLS. Pure Python. Order R1..R7; first violation wins per lane,
so each rejected lane carries exactly one rule citation.

Hard invariants (ULTIMATE_PRD §3.5 #4, restated):
  - Stage 4 final validation is pure-Python rules.
  - Anti-Replication: no monetary derivation, no price/margin/recommendation
    computation, no booking-outcome inference.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

from packages.core.models.conformal import RuleId, RuleViolation
from packages.core.models.ratesheet import (
    EquipmentType,
    LaneRecord,
    NormalizedRatesheet,
    RejectionRecord,
    SurchargeBasis,
)

# Pydantic already enforces these Literal sets at validation time. R6/R7 are
# kept as defense-in-depth checks in case a Phase 5+ relaxed model slips a
# wider value past validation.
_EQUIPMENT_TYPES: Final[frozenset[str]] = frozenset(
    EquipmentType.__args__  # type: ignore[attr-defined]
)
_SURCHARGE_BASES: Final[frozenset[str]] = frozenset(
    SurchargeBasis.__args__  # type: ignore[attr-defined]
)
_UNLOCODE_SHAPE: Final = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")

_RULE_DESCRIPTIONS: Final[dict[RuleId, str]] = {
    "port_unknown_unlocode": "origin or destination port code does not match UN/LOCODE shape",
    "negative_base_rate": "base_rate_usd is zero or negative",
    "validity_window_in_the_past": "validity_end is before today (UTC)",
    "validity_window_inverted": "validity_start is after validity_end",
    "transit_time_out_of_range": "transit_time_days outside the [1, 120] envelope",
    "equipment_type_unknown": "equipment_type not in the locked Literal set",
    "surcharge_basis_unknown": "surcharge applies_per not in the locked Literal set",
}


def _evaluate_lane(lane: LaneRecord, today: datetime) -> RuleViolation | None:
    """Apply R1..R7 to a single lane; return the first violation or None."""
    if not (
        _UNLOCODE_SHAPE.match(lane.origin_port.code)
        and _UNLOCODE_SHAPE.match(lane.destination_port.code)
    ):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=_RULE_DESCRIPTIONS["port_unknown_unlocode"],
        )
    if lane.base_rate_usd <= Decimal("0"):
        return RuleViolation(
            rule_id="negative_base_rate",
            rule_description=_RULE_DESCRIPTIONS["negative_base_rate"],
        )
    if lane.validity_end < today.date():
        return RuleViolation(
            rule_id="validity_window_in_the_past",
            rule_description=_RULE_DESCRIPTIONS["validity_window_in_the_past"],
        )
    if lane.validity_start > lane.validity_end:
        return RuleViolation(
            rule_id="validity_window_inverted",
            rule_description=_RULE_DESCRIPTIONS["validity_window_inverted"],
        )
    if lane.transit_time_days is not None and not 1 <= lane.transit_time_days <= 120:
        return RuleViolation(
            rule_id="transit_time_out_of_range",
            rule_description=_RULE_DESCRIPTIONS["transit_time_out_of_range"],
        )
    if lane.equipment_type not in _EQUIPMENT_TYPES:
        return RuleViolation(
            rule_id="equipment_type_unknown",
            rule_description=_RULE_DESCRIPTIONS["equipment_type_unknown"],
        )
    for surcharge in lane.surcharges:
        if surcharge.applies_per not in _SURCHARGE_BASES:
            return RuleViolation(
                rule_id="surcharge_basis_unknown",
                rule_description=_RULE_DESCRIPTIONS["surcharge_basis_unknown"],
            )
    return None


def apply_hard_rules(
    rs: NormalizedRatesheet,
    *,
    now: datetime | None = None,
) -> tuple[NormalizedRatesheet, list[RuleViolation]]:
    """Apply R1..R7 to every lane in the ratesheet.

    Returns the updated NormalizedRatesheet (with rejected lanes moved out of
    `lanes` and into `deterministically_rejected`) plus the list of violations
    in the order they fired (one per rejected lane).
    """
    today = now or datetime.now(UTC)
    surviving: list[LaneRecord] = []
    rejected: list[RejectionRecord] = list(rs.deterministically_rejected)
    violations: list[RuleViolation] = []

    for lane in rs.lanes:
        violation = _evaluate_lane(lane, today)
        if violation is None:
            surviving.append(lane)
            continue
        rejected.append(
            RejectionRecord(
                source_row_reference=lane.source_row_reference,
                rule_id=violation.rule_id,
                rule_description=violation.rule_description,
            )
        )
        violations.append(violation)

    updated = rs.model_copy(
        update={
            "lanes": surviving,
            "deterministically_rejected": rejected,
        }
    )
    return updated, violations
