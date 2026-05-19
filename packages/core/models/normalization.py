"""Phase 3 normalization models. Implements PHASE_3_SPEC.md §3.1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.core.models.ratesheet import LaneRecord, PortCode


class EnsembleVote(BaseModel):
    """One Pro-call output per (lane, temperature) sample.

    Phase 3 ships N=3 at temperatures (0.1, 0.5, 0.9); Phase 4 may widen the
    Literal to include 0.0 and 1.0 for the conditional correction pass.
    """

    model_config = ConfigDict(extra="forbid")

    sample_index: Literal[0, 1, 2, 3, 4]
    temperature: Literal[0.1, 0.5, 0.9]
    lane: LaneRecord
    raw_response_hash: str = Field(min_length=8, max_length=64)


class ConsensusResult(BaseModel):
    """Per-lane consensus output produced by majority-vote across votes."""

    model_config = ConfigDict(extra="forbid")

    lane_id: str
    consensus_lane: LaneRecord | None
    votes: list[EnsembleVote] = Field(min_length=3, max_length=5)
    agreement_per_field: dict[str, int] = Field(default_factory=dict)
    requires_review: bool
    review_reason: Literal[
        "no_majority",
        "port_obfuscation_unresolved",
        "agreement_clean",
    ]


class LaneGraphTransition(BaseModel):
    """One write into lane_graph_states (LangGraph audit log; ULTIMATE_PRD §3.6)."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    lane_id: str
    status: Literal[
        "parsed",
        "extracted",
        "candidate_normalized",
        "needs_reference_lookup",
        "needs_human_review",
        "validated",
        "rejected",
    ]
    state_json: dict[str, Any]
    version: int = Field(ge=1)
    updated_at: datetime


class ResolvedPortCode(BaseModel):
    """Port-resolution output: canonical UN/LOCODE plus the alias that produced it."""

    model_config = ConfigDict(extra="forbid")

    canonical: PortCode | None
    source_alias: str = Field(min_length=2, max_length=16)
    resolution_method: Literal[
        "direct_unlocode",
        "carrier_alias_table",
        "iata_fallback",
        "unresolved",
    ]
