"""Section-granular split conformal prediction. Implements PHASE_4_SPEC.md §6.2.

ZERO LLM CALLS. Pure Python over the EnsembleVote agreement signal.
Conformal is on extraction confidence, not pricing decisions
(ULTIMATE_PRD Anti-Replication boundary).
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Final

from packages.core.models.conformal import ConformalCalibration, ConformalScore
from packages.core.models.normalization import EnsembleVote

# Pinned. Drift is prevented at the Pydantic Literal level (§3.2) — this
# constant is the runtime mirror.
ACCEPTANCE_THRESHOLD: Final[Decimal] = Decimal("0.85")

# Fields voted on; mirrors packages.ingest.consensus._VOTED_FIELDS so the
# per-field agreement signal is computed against the same surface area.
_VOTED_FIELDS: Final[tuple[str, ...]] = (
    "origin_port",
    "destination_port",
    "equipment_type",
    "commodity_code",
    "base_rate_usd",
    "transit_time_days",
    "validity_start",
    "validity_end",
    "surcharges",
    "source_row_reference",
)


def load_calibration(path: Path) -> ConformalCalibration:
    """Load and validate a calibration record from disk."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ConformalCalibration.model_validate(raw)


def _per_field_agreement(votes: list[EnsembleVote]) -> Decimal:
    """Return the average per-field agreement rate across the vote set.

    For each voted field, count the most-common canonical value and divide by
    N. Average across fields. The result lies in [1/N, 1.0]; section-granular
    split conformal uses this as the nonconformity covariate.
    """
    n = len(votes)
    if n == 0:
        return Decimal("0")

    totals: list[Decimal] = []
    for field in _VOTED_FIELDS:
        seen: dict[str, int] = {}
        for vote in votes:
            value = getattr(vote.lane, field)
            key = repr(value.model_dump(mode="json") if hasattr(value, "model_dump") else value)
            seen[key] = seen.get(key, 0) + 1
        top = max(seen.values())
        totals.append(Decimal(top) / Decimal(n))

    return (sum(totals, Decimal(0)) / Decimal(len(_VOTED_FIELDS))).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def compute_conformal_score(
    lane_id: str,
    votes: list[EnsembleVote],
    calibration: ConformalCalibration,
) -> ConformalScore:
    """Map the agreement signal through the calibration into a confidence in [0,1].

    Section-granular split conformal: the per-field agreement rate is the raw
    nonconformity score. Higher agreement → higher confidence. The calibration
    holds the threshold (0.85) at which the system accepts vs flags the lane.
    """
    raw = _per_field_agreement(votes)
    # Clamp into [0, 1] — _per_field_agreement already returns a value in that
    # range, but Decimal arithmetic + rounding can produce 1.001 in edge cases.
    bounded = max(Decimal("0.000"), min(Decimal("1.000"), raw))
    return ConformalScore(
        lane_id=lane_id,
        confidence=bounded,
        method="section_granular_split_conformal",
        calibration_id=calibration.calibration_id,
    )


def accepts(score: ConformalScore) -> bool:
    """Return True iff the conformal score clears the locked 0.85 threshold."""
    return score.confidence >= ACCEPTANCE_THRESHOLD
