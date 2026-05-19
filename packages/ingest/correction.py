"""Conditional Pro correction pass. Implements PHASE_4_SPEC.md §6.3.

LLM-bearing path — gated on disagreement only (§4.4 / Wan et al. 2408.17017).
Runs the N=2 escalation ONLY when the Phase 3 N=3 ensemble produced no
majority. Unconditional escalation doubles cost without recall improvement
and breaks the Step 1C cost envelope.

HARD INVARIANTS:
  - Model = "gemini-3.1-pro-preview".
  - Temperatures = (0.0, 1.0). Endpoints only; the inner triple (0.1, 0.5, 0.9)
    is owned by Phase 3.
  - Final consensus is strict majority across the full five votes (3 from
    Phase 3 + 2 from this module). 5 // 2 + 1 = 3.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Literal

from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.normalization import ConsensusResult, EnsembleVote
from packages.core.models.ratesheet import LaneRecord
from packages.core.settings import Settings
from packages.ingest.consensus import majority_consensus

_log = logging.getLogger(__name__)

_MODEL_ID: Literal["gemini-3.1-pro-preview"] = "gemini-3.1-pro-preview"
_CORRECTION_TEMPERATURES: tuple[float, float] = (0.0, 1.0)
_PER_CALL_TIMEOUT_SECONDS = 15.0
_TOTAL_BUDGET_SECONDS = 30.0
_RETRY_BACKOFF_SECONDS = 0.5

_SYSTEM_INSTRUCTION = """You are a deterministic identifier disambiguator.

You receive a lane that the N=3 Pro ensemble failed to reach majority on.
Produce one LaneRecord JSON that conforms to the response_schema and reflects
the most defensible reading of the source data.

Hard rules:
- Do NOT compute, recommend, or derive any monetary value. base_rate_usd
  passes through unchanged from the prior votes.
- Do NOT invent port codes. If you cannot resolve a port to a canonical
  UN/LOCODE, return the raw alias as-is.
- Your output MUST conform to the provided response_schema.
"""


class CorrectionError(Exception):
    """Raised when the conditional correction pass cannot produce two valid votes."""


def _hash_response(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def _one_correction_call(
    client: Any,
    lane: LaneRecord,
    sample_index: Literal[3, 4],
    temperature: float,
) -> EnsembleVote:
    """Run a single Pro call at the endpoint temperature."""
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=LaneRecord.model_json_schema(),
        system_instruction=_SYSTEM_INSTRUCTION,
    )
    contents = (
        "Disambiguate this lane. The N=3 ensemble produced no majority. "
        "Return your best LaneRecord JSON.\n\n"
        f"Lane: {lane.model_dump_json()}"
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
                raise CorrectionError("empty correction response")
            parsed = json.loads(text)
            parsed.setdefault("lane_id", lane.lane_id)
            parsed.setdefault(
                "source_row_reference",
                lane.source_row_reference.model_dump(mode="json"),
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
            raise CorrectionError(f"correction timeout at T={temperature}") from exc
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if attempt == 0 and isinstance(status, int) and 500 <= status < 600:
                last_exc = exc
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise
    raise CorrectionError(str(last_exc) if last_exc else "unreachable")


async def conditional_correction(
    prior_consensus: ConsensusResult,
    settings: Settings,
) -> ConsensusResult:
    """Maybe run N=2 correction. Gated strictly on prior_consensus.requires_review.

    Returns the prior consensus unchanged when no escalation is warranted.
    Otherwise, runs two Pro calls at (0.0, 1.0), appends the new votes, and
    recomputes majority across all five.
    """
    if not prior_consensus.requires_review:
        return prior_consensus

    # Use the first prior vote's lane as the reference lane to escalate.
    lane = prior_consensus.votes[0].lane
    client = get_vertex_client(settings)

    coros = [
        _one_correction_call(client, lane, 3, _CORRECTION_TEMPERATURES[0]),
        _one_correction_call(client, lane, 4, _CORRECTION_TEMPERATURES[1]),
    ]
    results = await asyncio.wait_for(
        asyncio.gather(*coros, return_exceptions=True),
        timeout=_TOTAL_BUDGET_SECONDS,
    )
    new_votes: list[EnsembleVote] = []
    for r in results:
        if isinstance(r, BaseException):
            raise CorrectionError(f"correction call failed: {r}") from r
        new_votes.append(r)

    combined_votes = [*prior_consensus.votes, *new_votes]
    if len(combined_votes) != 5:
        raise CorrectionError(f"expected 5 votes post-correction, got {len(combined_votes)}")
    return majority_consensus(prior_consensus.lane_id, combined_votes)
