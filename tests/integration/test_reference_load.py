"""Integration test for the reference-data bulk load. PHASE_3_SPEC §8 criterion 2.

Skipped automatically when SOLVO_RUN_REFERENCE_LOAD_TESTS is unset — the test
requires a live Postgres + the generated CSVs. Run locally with:

    python data/_generate.py
    docker compose up -d postgres
    alembic upgrade head
    SOLVO_RUN_REFERENCE_LOAD_TESTS=1 pytest tests/integration/test_reference_load.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_should_run = os.getenv("SOLVO_RUN_REFERENCE_LOAD_TESTS") == "1"


@pytest.mark.skipif(not _should_run, reason="set SOLVO_RUN_REFERENCE_LOAD_TESTS=1 to enable")
@pytest.mark.asyncio
async def test_bulk_load_un_locode_idempotent() -> None:
    """Loading the CSV twice yields the same row count both times."""
    from packages.core.settings import get_settings
    from packages.reference.loader import bulk_load_un_locode

    csv_path = Path("data/un_locode_2024_2.csv")
    assert csv_path.exists(), "run `python data/_generate.py` first"
    dsn = get_settings().postgres_dsn_async
    first = await bulk_load_un_locode(dsn, csv_path)
    second = await bulk_load_un_locode(dsn, csv_path)
    assert first == second
    assert first >= 100_000
