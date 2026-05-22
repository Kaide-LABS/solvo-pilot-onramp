"""End-to-end Celery-driven pipeline regression test.

Implements PHASE_6_5_SPEC.md §6.4 + PHASE_6_6_SPEC.md §6.7 — the tests that
would have caught the four Stage F.3 defects across the two halts.

Gated behind `SOLVO_RUN_E2E_TESTS=1` because it requires a live compose
stack (postgres + redis + api + worker + dispatcher) and burns Vertex AI
quota. Local recipe:

    docker compose up -d --wait
    SOLVO_RUN_E2E_TESTS=1 pytest tests/integration/test_pipeline_e2e.py -q

The tests assert:

1. The 15-lane K+N Magic Moment fixture transitions a job from `pending`
   → `completed` within 200 s and produces output counts within the
   Phase 6.6 §6.4.3 bands (11 ±2 normalized, 0-3 flagged, 1-3 rejected).
   Without the Phase 6.5 per-task engine fix, tasks die on cross-loop
   SQLAlchemy errors and the job stays at `pending` indefinitely —
   catching Defect 1.

2. The job's outbox table contains exactly one `audit_log` row with
   `stage=validated` AND exactly one `slack_post` row whose payload has
   the requested channel and a non-empty `blocks` array. Without the
   Phase 6.5 `_validate` slack_post enqueue, the slack_post row is
   missing — catching Defect 3.

3. The dispatcher delivers the queued `slack_post` row to a recording
   stub of `chat_postMessage`. The bot must be invoked with the correct
   channel and non-empty blocks.

4. (Phase 6.6 §6.7) A `_normalize` task that raises `EnsembleError`
   leaves the job at `status='failed'` (not wedged at `normalizing`) AND
   writes an audit_log row with `stage='normalize_failed'`, no
   `/tmp/onramp/` substrings in the error_message (PII redaction holds).
   Catches Defect 6.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

_should_run = os.getenv("SOLVO_RUN_E2E_TESTS") == "1"
_API_BASE = os.getenv("SOLVO_E2E_API_BASE", "http://localhost:8080")
# Phase 6.6: happy path now drives the 15-lane K+N fixture (was the 3-lane
# `01_clean_excel.xlsx`). Spec §6.7 mandates this swap.
_FIXTURE = Path("fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx")
# Phase 6.6 §6.4.3: 180 s F.3.1 budget + 20 s test margin = 200 s deadline.
_POLL_DEADLINE_SECONDS = 200.0
_POLL_INTERVAL_SECONDS = 2.0


@pytest.fixture
def _compose_stack_ready() -> Iterator[None]:
    """Sanity-check the compose stack is up before exercising the pipeline."""
    if not _should_run:
        pytest.skip("set SOLVO_RUN_E2E_TESTS=1 to enable")
    try:
        r = httpx.get(f"{_API_BASE}/v1/health", timeout=5.0)
    except httpx.RequestError as exc:
        pytest.skip(f"api unreachable at {_API_BASE}: {exc}")
    if r.status_code != 200:
        pytest.skip(f"api unhealthy: status={r.status_code}")
    body = r.json()
    if body.get("status") != "healthy":
        pytest.skip(f"api validators failing: {body}")
    yield


def _submit_job(channel: str) -> str:
    """POST the fixture to /v1/intake/jobs and return the job_id."""
    assert _FIXTURE.exists(), f"missing fixture: {_FIXTURE}"
    with _FIXTURE.open("rb") as fh:
        response = httpx.post(
            f"{_API_BASE}/v1/intake/jobs",
            files={"upload": (_FIXTURE.name, fh, "application/octet-stream")},
            data={
                "prospect_id": "e2e-prospect-1",
                "prospect_name": "E2E Test Prospect",
                "operator_email": "e2e@kaide.so",
                "requested_slack_channel": channel,
                "priority": "normal",
            },
            timeout=30.0,
        )
    assert response.status_code == 202, response.text
    return str(response.json()["job_id"])


def _poll_until_completed(job_id: str) -> str:
    """Poll until the job is `completed` or `failed`, returning the final status."""
    deadline = time.monotonic() + _POLL_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        r = httpx.get(f"{_API_BASE}/v1/intake/jobs/{job_id}", timeout=5.0)
        if r.status_code == 200:
            status = r.json().get("status")
            if status in {"completed", "failed"}:
                return str(status)
        time.sleep(_POLL_INTERVAL_SECONDS)
    return "timeout"


async def _read_outbox_rows(job_id: str) -> list[dict[str, Any]]:
    """Query the outbox table directly for rows belonging to this job."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.core.db.base import OnrampOutbox
    from packages.core.db.session import make_async_engine
    from packages.core.settings import get_settings

    settings = get_settings()
    engine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            result = await session.execute(
                select(OnrampOutbox).where(OnrampOutbox.job_id == job_id)
            )
            return [
                {
                    "event_type": row.event_type,
                    "payload": row.payload,
                    "delivered_at": row.delivered_at,
                }
                for row in result.scalars().all()
            ]
    finally:
        await engine.dispose()


async def _read_output_counts(job_id: str) -> dict[str, int]:
    """Read the (lane_count, flagged_count, rejected_count) for a job."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.core.db.base import OnrampOutput
    from packages.core.db.session import make_async_engine
    from packages.core.settings import get_settings

    settings = get_settings()
    engine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = (
                await session.execute(
                    select(OnrampOutput).where(OnrampOutput.job_id == job_id)
                )
            ).scalar_one()
            return {
                "lane_count": int(row.lane_count or 0),
                "flagged_count": int(row.flagged_count or 0),
                "rejected_count": int(row.rejected_count or 0),
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kn_15_lane_reaches_completed_and_emits_slack_post(
    _compose_stack_ready: None,
) -> None:
    """End-to-end regression: 15-lane K+N fixture lands at `completed` with
    counts inside the Phase 6.6 §6.4.3 bands and queues a Slack post.
    """
    channel = "C-E2E-TEST"
    job_id = _submit_job(channel)

    final_status = _poll_until_completed(job_id)
    assert final_status == "completed", (
        f"job {job_id} stuck at status={final_status} — regression in Defect 1 "
        "(per-task engine) or Defect 5 (per-call Vertex client) likely"
    )

    # Phase 6.6 §6.4.3: 15-lane bands.
    counts = await _read_output_counts(job_id)
    assert 9 <= counts["lane_count"] <= 13, (
        f"normalized lane_count={counts['lane_count']} outside 9-13 band"
    )
    assert 0 <= counts["flagged_count"] <= 3, (
        f"flagged_count={counts['flagged_count']} outside 0-3 band"
    )
    assert 1 <= counts["rejected_count"] <= 3, (
        f"rejected_count={counts['rejected_count']} outside 1-3 band"
    )

    rows = await _read_outbox_rows(job_id)
    audit_validated = [
        r
        for r in rows
        if r["event_type"] == "audit_log"
        and isinstance(r["payload"], dict)
        and r["payload"].get("stage") == "validated"
    ]
    slack_posts = [r for r in rows if r["event_type"] == "slack_post"]

    assert len(audit_validated) == 1, (
        f"expected exactly one audit_log/validated row, got {len(audit_validated)}"
    )
    assert len(slack_posts) == 1, (
        f"expected exactly one slack_post row — regression in Defect 3 fix; got "
        f"{len(slack_posts)} (all rows: {[r['event_type'] for r in rows]})"
    )

    slack_payload = slack_posts[0]["payload"]
    assert isinstance(slack_payload, dict)
    assert slack_payload.get("channel") == channel
    blocks = slack_payload.get("blocks")
    assert isinstance(blocks, list) and len(blocks) > 0, "blocks must be non-empty"
    # Anti-Replication: no raw rate values embedded.
    serialized = json.dumps(blocks)
    assert "base_rate" not in serialized, "rate value leaked into Slack blocks"


@pytest.mark.asyncio
async def test_normalize_failure_surfaces_as_status_failed(
    _compose_stack_ready: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 6.6 §6.7 Defect 6 regression.

    Strategy (mechanism (a) per spec): seed an in-process `_normalize` call
    against the live postgres with `packages.ingest.normalizer.normalize_lanes`
    monkeypatched to raise `EnsembleError`. Assert the job row reaches
    `status='failed'` AND the outbox carries the `normalize_failed`
    audit_log row with PII-clean error_message.

    Runs in-process (not through the worker container) so the monkeypatch
    actually takes effect. The intake route side-effects (job row + staging
    file + ingress_received audit_log) are produced manually rather than via
    Celery — we want to test the failure-handler, not the Celery chain.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.core.db.base import OnrampJob, OnrampOutput
    from packages.core.db.session import make_async_engine
    from packages.core.models.ratesheet import (
        ExtractionMetadata,
        NormalizedRatesheet,
    )
    from packages.core.settings import get_settings
    from packages.ingest import normalizer as normalizer_mod
    from packages.ingest import tasks as tasks_mod
    from packages.ingest.normalizer import EnsembleError

    job_id = uuid.uuid4().hex
    settings = get_settings()
    engine = make_async_engine(settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a minimal job row + extraction OnrampOutput so _normalize has
    # something to read. Path under /tmp/onramp embedded in the failure
    # message proves the PII redaction works end-to-end.
    fake_path = f"/tmp/onramp/{job_id}/operator-private-file.xlsx"  # noqa: S108
    minimal_ratesheet = NormalizedRatesheet(
        lanes=[],
        flagged_for_review=[],
        deterministically_rejected=[],
        extraction_metadata=ExtractionMetadata(
            prospect_id="e2e-defect-6",
            source_filename="defect_6.xlsx",
            source_format="excel",
            extractor_model="gemini-3.1-flash-lite",
        ),
    )
    try:
        async with factory() as session, session.begin():
            await session.execute(
                pg_insert(OnrampJob)
                .values(
                    job_id=job_id,
                    prospect_id="e2e-defect-6",
                    prospect_name="Defect6 Probe",
                    input_hash=job_id,  # uniqueness guaranteed by uuid4
                    source_format="excel",
                    status="normalizing",
                )
                .on_conflict_do_nothing(index_elements=[OnrampJob.input_hash])
            )
            await session.execute(
                pg_insert(OnrampOutput).values(
                    job_id=job_id,
                    normalized_payload=minimal_ratesheet.model_dump(mode="json"),
                    lane_count=0,
                    flagged_count=0,
                    rejected_count=0,
                )
            )

        # Monkeypatch normalize_lanes to raise. The exception message embeds
        # the operator-private staging path; the audit_log redaction must
        # strip it down to `<staging>`.
        async def _raising_normalize_lanes(**_kwargs: Any) -> Any:
            raise EnsembleError(
                f"simulated Pro-call timeout reading {fake_path}"
            )

        monkeypatch.setattr(
            normalizer_mod, "normalize_lanes", _raising_normalize_lanes
        )

        # _normalize should propagate EnsembleError after writing failure
        # status in its own fresh transaction.
        with pytest.raises(EnsembleError):
            await tasks_mod._normalize(job_id)

        # Verify the durable failure signal.
        from sqlalchemy import select

        async with factory() as session:
            job_row = (
                await session.execute(
                    select(OnrampJob).where(OnrampJob.job_id == job_id)
                )
            ).scalar_one()
            assert job_row.status == "failed", (
                f"Defect 6 regression: job stuck at status={job_row.status!r} "
                "instead of 'failed'"
            )
            assert job_row.completed_at is not None

        rows = await _read_outbox_rows(job_id)
        normalize_failed_rows = [
            r
            for r in rows
            if r["event_type"] == "audit_log"
            and isinstance(r["payload"], dict)
            and r["payload"].get("stage") == "normalize_failed"
        ]
        assert len(normalize_failed_rows) == 1, (
            f"expected one audit_log/normalize_failed row, got "
            f"{len(normalize_failed_rows)}"
        )
        payload = normalize_failed_rows[0]["payload"]
        assert payload["error_type"] == "EnsembleError"
        assert payload["error_message"], "error_message must be non-empty"
        # PII redaction: the /tmp/onramp/... path must be scrubbed.
        assert "/tmp/onramp/" not in payload["error_message"], (  # noqa: S108
            f"staging path leaked into audit_log: {payload['error_message']!r}"
        )
        assert "<staging>" in payload["error_message"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dispatcher_delivers_slack_post(
    _compose_stack_ready: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stubs the Slack client, runs one drain tick, asserts the message went out.

    Runs in-process rather than through compose so we can inject the mock.
    The dispatcher's `_drain_once` is invoked directly with the live db/redis
    state populated by the prior test's job.
    """
    from packages.dispatcher import outbox_worker
    from packages.slack import client as slack_client_mod

    recorded: list[dict[str, Any]] = []

    class _RecordingClient:
        async def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
            recorded.append(kwargs)
            return {"ts": "1700000000.000001", "channel": kwargs["channel"]}

    def _fake_get_client(_settings: Any) -> _RecordingClient:
        return _RecordingClient()

    monkeypatch.setattr(slack_client_mod, "get_slack_client", _fake_get_client)

    from packages.core.settings import get_settings

    result = await outbox_worker._drain_once(get_settings())
    assert result["delivered"] >= 1, f"dispatcher drained nothing: {result}"

    slack_calls = [c for c in recorded if "blocks" in c]
    assert slack_calls, "no chat_postMessage with blocks recorded"
    call = slack_calls[-1]
    assert call["channel"].startswith("C-"), f"unexpected channel: {call['channel']}"
    assert isinstance(call.get("blocks"), list)
    assert len(call["blocks"]) > 0
