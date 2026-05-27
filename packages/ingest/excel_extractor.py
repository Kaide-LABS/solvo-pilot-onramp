"""Stage 2 — Excel extractor. Implements PHASE_2_SPEC.md §6.2.

Reads .xlsx via openpyxl (read_only, data_only), produces a structured cell
list (NOT the raw blob), and asks gemini-3.1-flash-lite to return a
NormalizedRatesheet that conforms to the strict-forbid response schema.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import orjson
from openpyxl import load_workbook

from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.ratesheet import ExtractionMetadata, NormalizedRatesheet
from packages.core.settings import Settings
from packages.ingest.prompts import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTIONS,
    USER_PROMPT_TEMPLATE,
    get_response_schema,
)

_log = logging.getLogger(__name__)

_CELL_LIMIT = 5_000
_VERTEX_BUDGET_SECONDS = 30.0
_RETRY_BACKOFF_SECONDS = 0.5
_MODEL_ID = "gemini-3.1-flash-lite"
_TEMPERATURE = 0.1


class ExcelTooLargeError(Exception):
    """Raised when the workbook exceeds the Phase 2 cell cap (5,000)."""


class ExtractionError(Exception):
    """Raised when Gemini Flash returned no parseable result within the budget."""


def _serialize_cell_value(value: Any) -> Any:
    """Coerce openpyxl cell values into JSON-safe primitives."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    # date, time, Decimal — coerce via str so the model sees stable text.
    return str(value)


def _build_cell_list(file_path: Path) -> list[dict[str, Any]]:
    """Walk the workbook and produce the cell list passed to Gemini.

    Enforces _CELL_LIMIT. Raises ExcelTooLargeError on overflow.
    """
    workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
    try:
        cells: list[dict[str, Any]] = []
        for sheet in workbook.worksheets:
            merged_ranges = (
                {r.coord: r.coord for r in sheet.merged_cells.ranges}
                if not workbook.read_only
                else {}
            )
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    coord = cell.coordinate
                    cells.append(
                        {
                            "sheet": sheet.title,
                            "row": cell.row,
                            "col": cell.column,
                            "coord": coord,
                            "value": _serialize_cell_value(cell.value),
                            "is_merged_anchor": coord in merged_ranges,
                            "merge_range": merged_ranges.get(coord),
                        }
                    )
                    if len(cells) > _CELL_LIMIT:
                        raise ExcelTooLargeError(
                            f"cell count exceeded {_CELL_LIMIT} (still counting at {coord})"
                        )
        return cells
    finally:
        workbook.close()


def _build_prompt(job_id: str, prospect_id: str, cells: list[dict[str, Any]]) -> str:
    """Render the user-prompt template with the JSON-serialized cell list."""
    return USER_PROMPT_TEMPLATE.format(
        job_id=job_id,
        prospect_id=prospect_id,
        prompt_version=PROMPT_VERSION,
        cells_json=orjson.dumps(cells).decode("utf-8"),
    )


async def _generate_with_retry(client: Any, contents: str, response_schema: dict[str, Any]) -> Any:
    """Call generate_content; retry once with 500ms backoff on transient 5xx errors."""
    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=response_schema,
        system_instruction=SYSTEM_INSTRUCTIONS,
    )
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_MODEL_ID,
                    contents=contents,
                    config=config,
                ),
                timeout=_VERTEX_BUDGET_SECONDS,
            )
        except TimeoutError:
            _log.warning("excel_extractor: Vertex AI timeout on attempt %d", attempt + 1)
            if attempt == 0:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise ExtractionError("Vertex AI exceeded the 30s budget") from None
        except Exception as exc:
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if attempt == 0 and isinstance(status, int) and 500 <= status < 600:
                _log.warning("excel_extractor: Vertex AI %s on attempt 1; retrying once", status)
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise
    raise ExtractionError("unreachable")


def _parse_response_text(response: Any) -> dict[str, Any]:
    """Extract the JSON body from a Gemini response object."""
    text = getattr(response, "text", None)
    if text is None:
        # Fall back to inspecting candidates / parts in case the SDK surface
        # changes between minor versions.
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            parts = getattr(getattr(cand, "content", None), "parts", None) or []
            for part in parts:
                inline = getattr(part, "text", None)
                if inline:
                    text = inline
                    break
            if text:
                break
    if not text:
        raise ExtractionError("Vertex AI returned no text content")
    return cast(dict[str, Any], json.loads(text))


async def extract_excel_payload(
    file_path: Path,
    job_id: str,
    prospect_id: str,
    settings: Settings,
) -> tuple[NormalizedRatesheet, ExtractionMetadata]:
    """Run Stage 2 extraction on the given .xlsx file.

    Returns the parsed NormalizedRatesheet plus its ExtractionMetadata. Raises
    ExcelTooLargeError on oversized workbooks and ExtractionError on Vertex AI
    failure or schema-violating model output.
    """
    cells = await asyncio.to_thread(_build_cell_list, file_path)
    contents = _build_prompt(job_id, prospect_id, cells)
    client = get_vertex_client(settings)
    response = await _generate_with_retry(client, contents, get_response_schema())
    body = _parse_response_text(response)

    # Force the metadata fields to known-good values so the upstream prompt
    # cannot smuggle a different model identifier or prompt version into the
    # provenance record.
    extracted_at = datetime.now(UTC)
    metadata = ExtractionMetadata(
        extractor_model=cast(Literal["gemini-3.1-flash-lite"], _MODEL_ID),
        extracted_at=extracted_at,
        prompt_version=PROMPT_VERSION,
        cell_count=len(cells),
    )

    # Overwrite extractor-supplied identifiers with the authoritative ones.
    body["job_id"] = job_id
    body["prospect_id"] = prospect_id
    body["extraction_metadata"] = metadata.model_dump(mode="json")
    body["schema_version"] = "onramp.v1"
    # Phase 7 §6.1.1 (Defect 18a): force-overwrite, not setdefault. The Stage 2
    # LLM occasionally smuggles non-empty values into these fields with
    # invented rule_ids like "INVALID_PORT_CODE". Stage 4 is the sole source
    # of rejections; conformal/flagged are populated downstream.
    body["conformal_scores"] = {}
    body["flagged_for_review"] = []
    body["deterministically_rejected"] = []

    payload = NormalizedRatesheet.model_validate(body)
    return payload, metadata
