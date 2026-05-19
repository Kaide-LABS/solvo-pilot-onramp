"""Stage 2 excel extractor tests with mocked Gemini Flash. PHASE_2_SPEC §8 criterion 2."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from packages.core.settings import get_settings
from packages.ingest import excel_extractor
from packages.ingest.excel_extractor import (
    ExcelTooLargeError,
    _build_cell_list,
    extract_excel_payload,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _canned_payload(job_id: str = "j1", prospect_id: str = "p123") -> dict[str, Any]:
    src_row = {"sheet_name": "Rates", "row_number": 2, "cell_reference": "A2:F2"}
    lane = {
        "lane_id": "L1",
        "origin_port": {"code": "NLRTM"},
        "destination_port": {"code": "USNYC"},
        "equipment_type": "40HC",
        "base_rate_usd": "2100",
        "surcharges": [],
        "validity_start": "2026-01-01",
        "validity_end": "2026-06-30",
        "source_row_reference": src_row,
    }
    return {
        "job_id": job_id,
        "prospect_id": prospect_id,
        "extraction_metadata": {
            "extractor_model": "gemini-3-flash-preview",
            "extracted_at": "2026-05-19T12:00:00+00:00",
            "prompt_version": "stage2.excel.v1",
            "cell_count": 1,
        },
        "lanes": [lane],
        "schema_version": "onramp.v1",
    }


class _MockModels:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls += 1
        return SimpleNamespace(text=json.dumps(_canned_payload()))


class _MockClient:
    def __init__(self) -> None:
        self.aio = SimpleNamespace(models=_MockModels())


@pytest.mark.parametrize(
    "filename",
    [
        "01_clean_excel.xlsx",
        "02_merged_cells.xlsx",
        "03_obfuscated_ports.xlsx",
        "04_mixed_currencies.xlsx",
        "05_mixed_units.xlsx",
    ],
)
@pytest.mark.asyncio
async def test_extract_smoke_per_fixture(
    monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    """Each fixture extracts cleanly with a single mocked Vertex AI call."""
    client = _MockClient()
    monkeypatch.setattr(excel_extractor, "get_vertex_client", lambda _settings: client)
    payload, metadata = await extract_excel_payload(
        FIXTURES / filename, "j1", "p123", get_settings()
    )
    assert client.aio.models.calls == 1
    assert payload.job_id == "j1"
    assert payload.prospect_id == "p123"
    assert metadata.extractor_model == "gemini-3-flash-preview"
    assert metadata.prompt_version == "stage2.excel.v1"
    assert payload.schema_version == "onramp.v1"


@pytest.mark.asyncio
async def test_extractor_returns_normalized_ratesheet(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mocked response goes through NormalizedRatesheet.model_validate."""
    client = _MockClient()
    monkeypatch.setattr(excel_extractor, "get_vertex_client", lambda _settings: client)
    payload, _ = await extract_excel_payload(
        FIXTURES / "01_clean_excel.xlsx", "j1", "p123", get_settings()
    )
    assert payload.lanes[0].origin_port.code == "NLRTM"
    assert payload.lanes[0].destination_port.code == "USNYC"


def test_cell_cap_enforced(tmp_path: Path) -> None:
    """A workbook exceeding 5,000 non-empty cells raises ExcelTooLargeError."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    # 6,000 single-cell rows blows past the cap on column A.
    for i in range(6_000):
        ws.cell(row=i + 1, column=1, value=f"v{i}")
    big = tmp_path / "big.xlsx"
    wb.save(big)
    with pytest.raises(ExcelTooLargeError):
        _build_cell_list(big)
