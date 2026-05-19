"""Stage 3 — N=3 Pro ensemble orchestrator. Implements PHASE_3_SPEC.md §6.1.

HARD INVARIANTS (ULTIMATE_PRD §3, Step 1B lock):
  - N = 3.  Not 1, not 2, not 5.
  - Temperatures = (0.1, 0.5, 0.9) in that order. No substitution.
  - Model = "gemini-3.1-pro-preview" (Vertex AI, europe-west4).
  - Singleton client via packages.compliance.vertex_client.get_vertex_client.
  - Majority-vote consensus. No weighted voting. No LLM-judged consensus.
  - The Pro system_instruction forbids rate generation; the model normalizes
    identifiers, never derives monetary values.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.normalization import ConsensusResult, EnsembleVote
from packages.core.models.ratesheet import (
    FlaggedLane,
    LaneRecord,
    NormalizedRatesheet,
)
from packages.core.settings import Settings
from packages.ingest.consensus import majority_consensus
from packages.ingest.port_resolver import resolve_port_code

_log = logging.getLogger(__name__)

# Locked ensemble configuration. NEVER mutate these literals.
_MODEL_ID: Literal["gemini-3.1-pro-preview"] = "gemini-3.1-pro-preview"
_TEMPERATURES: tuple[float, float, float] = (0.1, 0.5, 0.9)
_PER_CALL_TIMEOUT_SECONDS = 20.0
_TOTAL_BUDGET_SECONDS = 45.0
_RETRY_BACKOFF_SECONDS = 0.5

_SYSTEM_INSTRUCTION = """You are a deterministic identifier normalizer.

You receive a single freight lane that was extracted from a ratesheet, plus
reference candidates (UN/LOCODE entries that share the lane's country,
HS6 entries that share the lane's heading). Your job: emit one LaneRecord
JSON whose port codes, equipment_type, commodity_code, and surcharge codes
are normalized to canonical taxonomies.

Hard rules:
- Do NOT compute, recommend, or derive any monetary value. base_rate_usd
  passes through unchanged.
- Do NOT invent port codes. If you cannot map a raw port to a canonical
  UN/LOCODE present in the provided candidates, return the raw value as-is
  and let the deterministic resolver downstream flag it.
- Pass through validity_start, validity_end, transit_time_days, lane_id,
  source_row_reference, surcharges (other than surcharge code normalization)
  unchanged from the input lane.
- Your output MUST conform to the provided response_schema.
"""


class EnsembleError(Exception):
    """Raised when the N=3 ensemble cannot produce three valid votes."""


def _hash_response(text: str) -> str:
    """Return a short stable hash of the Pro response for vote provenance."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def _one_pro_call(
    client: Any,
    lane: LaneRecord,
    sample_index: Literal[0, 1, 2, 3, 4],
    temperature: float,
    reference_block: str,
) -> EnsembleVote:
    """Run a single Pro call at the given temperature and parse it into a vote.

    Locked invariant: only called from `_ensemble_for_lane` with temps drawn
    from the `_TEMPERATURES` triple. Float typing here is forced by PEP 586
    (Literal disallows floats); the (0.1, 0.5, 0.9) lock lives in module scope.
    """
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=float(temperature),
        response_mime_type="application/json",
        response_schema=LaneRecord.model_json_schema(),
        system_instruction=_SYSTEM_INSTRUCTION,
    )
    contents = (
        f"Lane (post-extraction):\n{lane.model_dump_json()}\n\n"
        f"Reference candidates:\n{reference_block}"
    )

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_MODEL_ID, contents=contents, config=config
                ),
                timeout=_PER_CALL_TIMEOUT_SECONDS,
            )
            text = getattr(response, "text", None) or ""
            if not text:
                raise EnsembleError("empty Pro response")
            parsed = json.loads(text)
            parsed.setdefault("lane_id", lane.lane_id)
            parsed.setdefault(
                "source_row_reference", lane.source_row_reference.model_dump(mode="json")
            )
            voted_lane = LaneRecord.model_validate(parsed)
            return EnsembleVote(
                sample_index=sample_index,
                temperature=temperature,
                lane=voted_lane,
                raw_response_hash=_hash_response(text),
            )
        except TimeoutError as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise EnsembleError(f"Pro call timeout at T={temperature}") from exc
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if attempt == 0 and isinstance(status, int) and 500 <= status < 600:
                _log.warning("normalizer: Pro 5xx at T=%s on attempt 1; retrying", temperature)
                last_exc = exc
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise
    raise EnsembleError(str(last_exc) if last_exc else "unreachable")


def _reference_block_for(lane: LaneRecord) -> str:
    """Compose the per-lane reference snippet passed to Pro.

    Phase 3 ships a minimal placeholder string. Phase 4 / Step 3B may expand
    this to include matched UN/LOCODE rows by country and HS6 rows by heading.
    """
    return json.dumps(
        {
            "country_origin_hint": lane.origin_port.code[:2]
            if len(lane.origin_port.code) >= 2
            else None,
            "country_destination_hint": lane.destination_port.code[:2]
            if len(lane.destination_port.code) >= 2
            else None,
            "hs6_heading_hint": lane.commodity_code[:4]
            if lane.commodity_code and len(lane.commodity_code) >= 4
            else None,
        }
    )


async def _ensemble_for_lane(client: Any, lane: LaneRecord) -> ConsensusResult:
    """Run three Pro calls in parallel and aggregate via majority vote."""
    reference_block = _reference_block_for(lane)
    coros = [
        _one_pro_call(client, lane, cast(Literal[0, 1, 2, 3, 4], i), temp, reference_block)
        for i, temp in enumerate(_TEMPERATURES)
    ]
    votes_or_exc = await asyncio.wait_for(
        asyncio.gather(*coros, return_exceptions=True),
        timeout=_TOTAL_BUDGET_SECONDS,
    )
    votes: list[EnsembleVote] = []
    for v in votes_or_exc:
        if isinstance(v, BaseException):
            raise EnsembleError(f"ensemble call failed: {v}") from v
        votes.append(v)
    if len(votes) != 3:
        raise EnsembleError(f"expected 3 votes, got {len(votes)}")
    return majority_consensus(lane.lane_id, votes)


async def _persist_consensus_votes(
    session: AsyncSession,
    job_id: str,
    consensus_results: list[ConsensusResult],
) -> None:
    """Phase 5 carry-forward: persist EnsembleVote rows into onramp_conformal_scores.

    The `confidence` column is preliminary (0.000); validate_output_task
    overwrites it with the calibrated conformal score from
    packages.ingest.conformal.
    """
    from decimal import Decimal

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from packages.core.db.base import OnrampConformalScore

    for consensus in consensus_results:
        snapshot = {
            "consensus": consensus.model_dump(mode="json"),
            "votes": [v.model_dump(mode="json") for v in consensus.votes],
        }
        await session.execute(
            pg_insert(OnrampConformalScore)
            .values(
                job_id=job_id,
                lane_id=consensus.lane_id,
                confidence=Decimal("0.000"),
                ensemble_votes=snapshot,
            )
            .on_conflict_do_update(
                index_elements=[
                    OnrampConformalScore.job_id,
                    OnrampConformalScore.lane_id,
                ],
                set_={
                    "confidence": Decimal("0.000"),
                    "ensemble_votes": snapshot,
                },
            )
        )


async def normalize_lanes(
    job_id: str,
    extraction: NormalizedRatesheet,
    session: AsyncSession,
    settings: Settings,
) -> tuple[NormalizedRatesheet, list[ConsensusResult]]:
    """Run Stage 3 across every lane in the extraction payload.

    Returns the updated NormalizedRatesheet (lanes possibly with resolved port
    codes, flagged_for_review extended) plus the per-lane consensus results
    for the audit trail.
    """
    client = get_vertex_client(settings)
    consensus_results: list[ConsensusResult] = []
    final_lanes: list[LaneRecord] = []
    flags = list(extraction.flagged_for_review)

    for lane in extraction.lanes:
        consensus = await _ensemble_for_lane(client, lane)
        consensus_results.append(consensus)

        if consensus.consensus_lane is None:
            flags.append(
                FlaggedLane(
                    lane=lane,
                    reason="no_majority",
                    confidence=None,
                )
            )
            continue

        # Port-code resolution on the consensus lane (deterministic anchor §3.5).
        resolved_lane = consensus.consensus_lane
        origin = await resolve_port_code(resolved_lane.origin_port.code, session)
        destination = await resolve_port_code(resolved_lane.destination_port.code, session)
        if origin.canonical is None or destination.canonical is None:
            flags.append(
                FlaggedLane(
                    lane=resolved_lane,
                    reason="port_obfuscation_unresolved",
                    confidence=None,
                )
            )
            continue

        final_lane = resolved_lane.model_copy(
            update={
                "origin_port": origin.canonical,
                "destination_port": destination.canonical,
            }
        )
        final_lanes.append(final_lane)

    updated = extraction.model_copy(
        update={
            "lanes": final_lanes,
            "flagged_for_review": flags,
            "extraction_metadata": extraction.extraction_metadata.model_copy(
                update={"extracted_at": datetime.now(UTC)}
            ),
        }
    )
    return updated, consensus_results
