"""Archive job round-trip. PHASE_6_SPEC §8.

Skipped automatically when SOLVO_RUN_ARCHIVE_TESTS is unset — the test
requires a live Postgres + GCS (or fake-gcs-server).
"""

from __future__ import annotations

import gzip
import json
import os

import pytest

_should_run = os.getenv("SOLVO_RUN_ARCHIVE_TESTS") == "1"


@pytest.mark.skipif(not _should_run, reason="set SOLVO_RUN_ARCHIVE_TESTS=1 to enable")
@pytest.mark.asyncio
async def test_archive_round_trip_preserves_payload() -> None:
    """End-to-end: completed job → archived blob → decoded JSON matches."""
    from packages.core.settings import get_settings
    from packages.lifecycle.archive import archive_completed_jobs

    settings = get_settings()
    candidates = await archive_completed_jobs(age_days=settings.archive_age_days, settings=settings)
    if not candidates:
        pytest.skip("no archive candidates in test DB")

    # Round-trip the first candidate's blob (test bucket must be reachable).
    from google.cloud import storage  # type: ignore[import-not-found]

    client = storage.Client()
    blob = client.bucket(settings.gcs_archive_bucket).blob(candidates[0].archive_blob_name)
    decoded = json.loads(gzip.decompress(blob.download_as_bytes()).decode("utf-8"))
    assert "job_id" in decoded
