"""Clarification phrasing node. Implements PHASE_4_SPEC.md §6.4.

LLM-bearing, text-only. Returns one short English sentence asking the
operator what to clarify with the prospect. NEVER returns a numeric value —
the post-processor rejects any digit in the output and falls back to a
non-numeric prompt.

Per ULTIMATE_PRD Anti-Replication boundary: clarification text NEVER
suggests a rate, margin, price, or any market-clearing decision.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.ratesheet import FlaggedLane
from packages.core.settings import Settings

_log = logging.getLogger(__name__)

_MODEL_ID = "gemini-3.1-pro-preview"
_TEMPERATURE = 0.2
_TIMEOUT_SECONDS = 10.0
_MAX_OUTPUT_CHARS = 240

# Detects ANY digit, integer or decimal. A successful match means the model
# proposed a numeric value — we reject it wholesale.
_NUMERIC_LEAK_RE = re.compile(r"\d")

_FALLBACK_PROMPT = "Ask the prospect to confirm the ambiguous field; do not suggest a value."

_SYSTEM_INSTRUCTION = """You write one short English sentence asking what to clarify.

You receive a flagged lane and the reason it was flagged. Produce a single
sentence (under 240 characters) telling the operator what to ASK the prospect.

Hard rules:
- NEVER include a number, integer, decimal, currency amount, rate, port code
  numeric prefix, percentage, or any digit at all.
- NEVER suggest a value to fill in. Only describe what to ask.
- NEVER recommend a price, margin, surcharge amount, or any monetary figure.
- If you cannot phrase the question without numbers, return:
  "Ask the prospect to clarify the ambiguous field; do not suggest a value."
"""


def _strip_numerics(text: str) -> str:
    """Return the fallback prompt if `text` contains any digit; otherwise text."""
    if _NUMERIC_LEAK_RE.search(text):
        _log.warning("clarification: numeric leak detected — using fallback")
        return _FALLBACK_PROMPT
    return text


async def draft_clarification(
    flagged: FlaggedLane,
    settings: Settings,
) -> str:
    """Draft a one-sentence clarification prompt for the flagged lane.

    Returns a string ≤ 240 characters with zero digits. On LLM error or
    numeric-leak detection, returns the fallback prompt.
    """
    from google.genai import types

    client: Any = get_vertex_client(settings)
    config = types.GenerateContentConfig(
        temperature=_TEMPERATURE,
        response_mime_type="text/plain",
        system_instruction=_SYSTEM_INSTRUCTION,
    )
    contents = (
        f"Flagged lane reason: {flagged.reason}.\n"
        f"Lane summary: origin={flagged.lane.origin_port.code}, "
        f"destination={flagged.lane.destination_port.code}, "
        f"equipment={flagged.lane.equipment_type}.\n"
        "Write one short clarification question."
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(model=_MODEL_ID, contents=contents, config=config),
            timeout=_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        _log.warning("clarification: Pro call failed: %s", exc)
        return _FALLBACK_PROMPT

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        return _FALLBACK_PROMPT
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS]
        _log.warning("clarification: output truncated to %d chars", _MAX_OUTPUT_CHARS)
    return _strip_numerics(text)
