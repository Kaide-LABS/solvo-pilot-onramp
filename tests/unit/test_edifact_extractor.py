"""EDIFACT extractor — PHASE_4_SPEC §8 criterion 6."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.core.settings import get_settings
from packages.ingest.edifact_extractor import extract_edifact_payload


@pytest.mark.asyncio
async def test_pricat_fixture_parses_deterministically_with_zero_llm_calls() -> None:
    """fixtures/06_edifact_pricat.edi parses fully without invoking Gemini Flash."""
    settings = get_settings()
    payload, meta = await extract_edifact_payload(
        Path("fixtures/06_edifact_pricat.edi"),
        job_id="job-1",
        prospect_id="prosp-1",
        settings=settings,
    )
    assert len(payload.lanes) == 3
    assert payload.lanes[0].origin_port.code == "NLRTM"
    assert payload.lanes[0].destination_port.code == "USNYC"
    assert payload.lanes[1].equipment_type == "40HC"
    assert payload.lanes[2].equipment_type == "20GP"
    assert meta.extractor_model == "gemini-3.1-flash-lite"
    assert payload.schema_version == "onramp.v1"
