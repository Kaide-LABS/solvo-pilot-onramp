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
    """Apply R1..R7 to a single lane; return the first violation or None.

    Phase 6.9 (§6.2): each branch composes a value-citing `rule_description`
    from the lane's actual fields (bad port code, negative rate, past date,
    etc.) so the rejection record carries real provenance, not just a static
    label. The `_RULE_DESCRIPTIONS` dict above remains as the rule-category
    catalogue (used for audit-log grouping) but is no longer the emitted text.
    """
    if not _UNLOCODE_SHAPE.match(lane.origin_port.code):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=(
                f"origin port code {lane.origin_port.code!r} does not match the "
                f"UN/LOCODE shape ^[A-Z]{{2}}[A-Z0-9]{{3}}$"
            ),
        )
    if not _UNLOCODE_SHAPE.match(lane.destination_port.code):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=(
                f"destination port code {lane.destination_port.code!r} does not "
                f"match the UN/LOCODE shape ^[A-Z]{{2}}[A-Z0-9]{{3}}$"
            ),
        )
    if lane.base_rate_usd <= Decimal("0"):
        return RuleViolation(
            rule_id="negative_base_rate",
            rule_description=(
                f"base_rate_usd={lane.base_rate_usd} is zero or negative; "
                f"R2 requires a strictly positive USD amount"
            ),
        )
    if lane.validity_end < today.date():
        return RuleViolation(
            rule_id="validity_window_in_the_past",
            rule_description=(
                f"validity_end={lane.validity_end.isoformat()} is before "
                f"today ({today.date().isoformat()} UTC); rate is stale"
            ),
        )
    if lane.validity_start > lane.validity_end:
        return RuleViolation(
            rule_id="validity_window_inverted",
            rule_description=(
                f"validity_start={lane.validity_start.isoformat()} is after "
                f"validity_end={lane.validity_end.isoformat()}"
            ),
        )
    if lane.transit_time_days is not None and not 1 <= lane.transit_time_days <= 120:
        return RuleViolation(
            rule_id="transit_time_out_of_range",
            rule_description=(
                f"transit_time_days={lane.transit_time_days} falls outside the [1, 120] envelope"
            ),
        )
    if lane.equipment_type not in _EQUIPMENT_TYPES:
        return RuleViolation(
            rule_id="equipment_type_unknown",
            rule_description=(
                f"equipment_type={lane.equipment_type!r} is not in the locked "
                f"Literal set {sorted(_EQUIPMENT_TYPES)}"
            ),
        )
    for surcharge in lane.surcharges:
        if surcharge.applies_per not in _SURCHARGE_BASES:
            return RuleViolation(
                rule_id="surcharge_basis_unknown",
                rule_description=(
                    f"surcharge {surcharge.code!r}.applies_per="
                    f"{surcharge.applies_per!r} not in locked Literal set "
                    f"{sorted(_SURCHARGE_BASES)}"
                ),
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
                lane_id=lane.lane_id,
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
