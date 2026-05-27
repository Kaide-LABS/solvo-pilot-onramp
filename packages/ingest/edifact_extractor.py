"""Stage 2 EDIFACT branch. Implements PHASE_4_SPEC.md §6.5.

DETERMINISTIC FIRST. `pydifact` tokenizes the PRICAT message; the LLM is
invoked ONLY when a segment grouping is ambiguous after deterministic parsing.
A fully-deterministic parse skips the Flash call entirely — Anti-Replication
prefers determinism whenever possible.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from pydifact.segmentcollection import Interchange

from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.ratesheet import (
    ExtractionMetadata,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
)
from packages.core.settings import Settings

_log = logging.getLogger(__name__)

_MODEL_ID: Literal["gemini-3.1-flash-lite"] = "gemini-3.1-flash-lite"
_TEMPERATURE = 0.0  # purely structural extraction for EDIFACT
_TIMEOUT_SECONDS = 20.0

_PROMPT_VERSION = "stage2.edifact.v1"

_SYSTEM_INSTRUCTION = """You disambiguate EDIFACT PRICAT segment groupings.

You receive a list of pre-tokenized segments and a question about which
segments belong together as one lane. Return a single LaneRecord JSON. Never
invent values; only group what is present.
"""


class EdifactExtractionError(Exception):
    """Raised when neither deterministic nor LLM-assisted parsing produced lanes."""


def _segment_to_dict(segment: Any) -> dict[str, Any]:
    """Serialize one pydifact segment into a JSON-safe dict."""
    return {"tag": segment.tag, "elements": list(segment.elements)}


# Phase 7 §6.2 (Defect 18b): UN/EDIFACT DTM qualifier map.
# 36  = end-of-validity (per UN/EDIFACT D.96A)
# 137 = document/message date/time (used here as start-of-validity)
# 35  = delivery date/time, actual
# 9   = processing date/time
_DTM_QUALIFIER_END = "36"
_DTM_QUALIFIER_START = "137"


def _parse_dtm_segment(elements: list[Any]) -> tuple[str | None, date | None]:
    """Return (qualifier, parsed_date) for a DTM segment, or (None, None).

    DTM segments look like `DTM+<qualifier>:<value>:<format>` where format=102
    is CCYYMMDD per UN/EDIFACT D.96A.
    """
    if not elements:
        return None, None
    first = elements[0]
    if isinstance(first, (list, tuple)):
        parts = [str(p).strip() for p in first]
    else:
        parts = [p.strip() for p in str(first).split(":")]
    if len(parts) < 2:
        return None, None
    qualifier = parts[0]
    value = parts[1]
    fmt = parts[2] if len(parts) >= 3 else "102"
    if fmt != "102" or len(value) != 8:
        return qualifier, None
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return qualifier, None
    return qualifier, parsed


def _extract_interchange_validity(segments: list[Any]) -> tuple[date | None, date | None]:
    """Scan all segments for DTM qualifier-36 (end) and 137 (start) dates.

    Phase 7 §6.2 (Defect 18b) fix: the cluster loop discards pre-LIN segments,
    so DTM+36 / DTM+137 that appear before the first LIN are lost. Scan the
    full interchange up-front and return the latest end-of-validity and start
    of validity found. Returns (start, end).
    """
    start_date: date | None = None
    end_date: date | None = None
    for seg in segments:
        if seg.tag != "DTM":
            continue
        qualifier, parsed = _parse_dtm_segment(list(seg.elements))
        if parsed is None:
            continue
        if qualifier == _DTM_QUALIFIER_END:
            end_date = parsed
        elif qualifier == _DTM_QUALIFIER_START:
            start_date = parsed
    return start_date, end_date


def _parse_lid_segment(elements: list[Any], sheet_label: str, row_index: int) -> LaneRecord | None:
    """Attempt to read a single LIN-rooted lane out of a pre-tokenized cluster.

    Returns None when any required field is absent — the caller falls back to
    the LLM disambiguator for that cluster.
    """
    try:
        origin = str(elements[0]).strip().upper()
        destination = str(elements[1]).strip().upper()
        equipment = str(elements[2]).strip().upper()
        base_rate_raw = str(elements[3]).strip()
        validity_start_raw = str(elements[4]).strip()
        validity_end_raw = str(elements[5]).strip()
    except (IndexError, ValueError):
        return None
    if (
        len(origin) != 5
        or len(destination) != 5
        or equipment
        not in {
            "20GP",
            "40GP",
            "40HC",
            "20RF",
            "40RF",
            "OOG",
            "BULK",
        }
    ):
        return None
    try:
        base_rate = Decimal(base_rate_raw)
        validity_start = date.fromisoformat(validity_start_raw)
        validity_end = date.fromisoformat(validity_end_raw)
    except (ValueError, ArithmeticError):
        return None
    return LaneRecord(
        lane_id=f"edi-row-{row_index}",
        origin_port=PortCode(code=origin),
        destination_port=PortCode(code=destination),
        equipment_type=cast(
            Literal["20GP", "40GP", "40HC", "20RF", "40RF", "OOG", "BULK"], equipment
        ),
        commodity_code=None,
        base_rate_usd=base_rate,
        surcharges=[],
        transit_time_days=None,
        validity_start=validity_start,
        validity_end=validity_end,
        source_row_reference=SourceRow(
            sheet_name=sheet_label, row_number=row_index, cell_reference=f"LIN:{row_index}"
        ),
    )


async def _disambiguate_via_flash(
    client: Any, segments: list[dict[str, Any]], lane_id: str
) -> LaneRecord | None:
    """Ask Gemini Flash to disambiguate an unparseable segment cluster."""
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=LaneRecord.model_json_schema(),
        system_instruction=_SYSTEM_INSTRUCTION,
    )
    contents = (
        f"Cluster lane_id={lane_id}\nSegments:\n{json.dumps(segments)}\nReturn one LaneRecord JSON."
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(model=_MODEL_ID, contents=contents, config=config),
            timeout=_TIMEOUT_SECONDS,
        )
        text = getattr(response, "text", None) or ""
        if not text:
            return None
        parsed = json.loads(text)
        return LaneRecord.model_validate(parsed)
    except Exception as exc:
        _log.warning("edifact: Flash disambiguation failed: %s", exc)
        return None


async def extract_edifact_payload(
    file_path: Path,
    job_id: str,
    prospect_id: str,
    settings: Settings,
) -> tuple[NormalizedRatesheet, ExtractionMetadata]:
    """Parse the EDIFACT PRICAT file and return a NormalizedRatesheet.

    Deterministic-first: LIN-rooted clusters are tokenized and parsed in pure
    Python. Only clusters that fail the deterministic shape check fall through
    to Gemini Flash at temperature 0.0.
    """
    raw = file_path.read_text(encoding="utf-8", errors="strict")
    interchange = Interchange.from_str(raw)
    segments = list(interchange.segments)

    # Phase 7 §6.2 (Defect 18b): pre-LIN DTM segments (qualifier 36 / 137)
    # were discarded by the cluster loop. Capture them up-front so we can
    # override any Flash-hallucinated validity dates and supply defaults to
    # the deterministic LIN parser when the LIN itself lacks date elements.
    interchange_start, interchange_end = _extract_interchange_validity(segments)

    # Group adjacent segments into lane clusters: a cluster spans from one LIN
    # to the next LIN or to UNT (message trailer).
    clusters: list[list[Any]] = []
    current: list[Any] = []
    for seg in segments:
        if seg.tag == "LIN":
            if current:
                clusters.append(current)
            current = [seg]
        elif seg.tag == "UNT":
            if current:
                clusters.append(current)
            current = []
            break
        else:
            if current:
                current.append(seg)
    if current:
        clusters.append(current)

    sheet_label = file_path.stem
    lanes: list[LaneRecord] = []
    flash_calls = 0

    for idx, cluster in enumerate(clusters):
        head = cluster[0]
        # Per-cluster DTM scan (DTMs may also live inside a cluster).
        cluster_start, cluster_end = _extract_interchange_validity(cluster)
        effective_start = cluster_start or interchange_start
        effective_end = cluster_end or interchange_end

        lane = _parse_lid_segment(list(head.elements), sheet_label, idx + 1)
        if lane is not None:
            lanes.append(lane)
            continue
        # Deterministic parse failed — invoke Flash as a fallback.
        client = get_vertex_client(settings)
        disambiguated = await _disambiguate_via_flash(
            client,
            [_segment_to_dict(s) for s in cluster],
            lane_id=f"edi-row-{idx + 1}",
        )
        flash_calls += 1
        if disambiguated is not None:
            # Phase 7 §6.2 (Defect 18b): authoritative DTM dates override any
            # Flash-hallucinated validity_start/end. Flash routinely invents
            # past dates ("2023-12-31") despite the fixture's future-dated
            # DTM+36 segment.
            update_payload: dict[str, Any] = {}
            if effective_start is not None:
                update_payload["validity_start"] = effective_start
            if effective_end is not None:
                update_payload["validity_end"] = effective_end
            if update_payload:
                disambiguated = disambiguated.model_copy(update=update_payload)
            lanes.append(disambiguated)

    if not lanes:
        raise EdifactExtractionError("no lanes parseable from EDIFACT input")

    metadata = ExtractionMetadata(
        extractor_model=_MODEL_ID,
        extracted_at=datetime.now(UTC),
        prompt_version=_PROMPT_VERSION,
        cell_count=len(segments),
    )
    rs = NormalizedRatesheet(
        job_id=job_id,
        prospect_id=prospect_id,
        extraction_metadata=metadata,
        lanes=lanes,
        conformal_scores={},
        flagged_for_review=[],
        deterministically_rejected=[],
        schema_version="onramp.v1",
    )
    _log.info(
        "edifact: parsed %d lanes (deterministic=%d, flash=%d)",
        len(lanes),
        len(lanes) - flash_calls,
        flash_calls,
    )
    return rs, metadata
