"""Majority-vote consensus across N ensemble samples. Implements PHASE_3_SPEC §6.2.

Pure-Python set counting. ZERO LLM calls — no confidence weighting, no
LLM-judged consensus, no soft self-consistency. The deterministic-anchor
invariant requires the consensus decision to be inspectable from source.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from packages.core.models.normalization import ConsensusResult, EnsembleVote
from packages.core.models.ratesheet import LaneRecord

# Fields voted on independently. Keep this list explicit rather than reflective
# so the audit trail shows exactly which fields were consensused on each cycle.
_VOTED_FIELDS = (
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


def _canonical(value: Any) -> str:
    """Coerce a Pydantic-modeled value into a hashable canonical form.

    Decimal → string preserves sign + precision; lists (surcharges) are
    compared as a sorted multiset of their canonical forms; nested BaseModels
    use model_dump(mode='json') so two semantically equal models hash equally.
    """
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return repr(_canonical(dumped))
    if isinstance(value, list):
        return repr(sorted(_canonical(item) for item in value))
    if isinstance(value, dict):
        return repr(sorted((k, _canonical(v)) for k, v in value.items()))
    if isinstance(value, Decimal):
        return str(value)
    return repr(value)


def majority_consensus(lane_id: str, votes: list[EnsembleVote]) -> ConsensusResult:
    """Compute strict majority consensus across the N votes for one lane.

    For each LaneRecord field, the canonical value with the highest count is
    selected only if it is held by a strict majority (> N/2). If any field
    fails to reach a strict majority, the consensus_lane is None and the
    lane is flagged with reason='no_majority'.
    """
    if not votes:
        raise ValueError("majority_consensus requires at least one vote")

    n = len(votes)
    majority_threshold = (n // 2) + 1
    selected: dict[str, Any] = {}
    agreement_per_field: dict[str, int] = {}

    for field in _VOTED_FIELDS:
        counter: Counter[str] = Counter()
        canon_to_value: dict[str, Any] = {}
        for vote in votes:
            value = getattr(vote.lane, field)
            key = _canonical(value)
            counter[key] += 1
            canon_to_value[key] = value
        top_key, top_count = counter.most_common(1)[0]
        agreement_per_field[field] = top_count
        if top_count >= majority_threshold:
            selected[field] = canon_to_value[top_key]
        else:
            # No field-level majority — entire lane is flagged.
            return ConsensusResult(
                lane_id=lane_id,
                consensus_lane=None,
                votes=votes,
                agreement_per_field=agreement_per_field,
                requires_review=True,
                review_reason="no_majority",
            )

    # All fields reached majority → reconstruct the consensus lane.
    consensus_lane = LaneRecord(lane_id=lane_id, **selected)
    return ConsensusResult(
        lane_id=lane_id,
        consensus_lane=consensus_lane,
        votes=votes,
        agreement_per_field=agreement_per_field,
        requires_review=False,
        review_reason="agreement_clean",
    )
