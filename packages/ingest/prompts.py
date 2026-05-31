"""Stage 2 prompt templates and response schemas. Implements PHASE_2_SPEC.md §6.2."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from packages.core.models.ratesheet import NormalizedRatesheet

PROMPT_VERSION = "stage2.excel.v2"

SYSTEM_INSTRUCTIONS = """You are a deterministic data normalizer for ocean freight ratesheets.
You receive a JSON array of cells extracted from a single spreadsheet, where each cell is
{sheet, row, col, value, is_merged_anchor, merge_range}.

Your job is to produce a NormalizedRatesheet JSON object that conforms exactly to the
provided response schema. Strict rules:

- Output only data present in the input cells. Do NOT invent rates, port codes,
  validity dates, or surcharges.
- Do NOT compute, guess, or derive any monetary value. Pass source numbers
  through unchanged. No rate generation. No advice. No suggestions.
- Use UN/LOCODE format for ports when the source clearly contains one
  (5 characters: two-letter country plus three-letter location).
  Carrier-internal port aliases (e.g., "BSAS", "NYC") flow through as-is —
  they will be resolved in a later normalization stage.
- equipment_type must be one of: 20GP, 40GP, 40HC, 20RF, 40RF, OOG, BULK.
- Omit a row only when it contains no lane data at all — for example, blank
  rows, section headers, or rows missing both port columns AND the rate
  column. If a row has a port column populated, emit a lane for it.
- `deterministically_rejected`, `flagged_for_review`, and `conformal_scores`
  MUST be empty arrays/dicts in your response. Any content you place there
  will be erased before downstream processing.
- schema_version MUST be exactly "onramp.v1".
"""

USER_PROMPT_TEMPLATE = """Extract lane records from this spreadsheet.

job_id: {job_id}
prospect_id: {prospect_id}
prompt_version: {prompt_version}

Cells:
{cells_json}
"""


@lru_cache(maxsize=1)
def get_response_schema() -> dict[str, Any]:
    """Return the cached JSON schema for NormalizedRatesheet.

    Pydantic's model_json_schema() is the canonical source — Gemini's
    response_schema accepts the same draft.
    """
    return NormalizedRatesheet.model_json_schema()
