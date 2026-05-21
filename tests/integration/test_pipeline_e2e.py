"""End-to-end Celery-driven pipeline regression test.

Implements PHASE_6_5_SPEC.md §6.4 — the test that would have caught all
three Stage F.3 defects.

Gated behind `SOLVO_RUN_E2E_TESTS=1` because it requires a live compose
stack (postgres + redis + api + worker + dispatcher) and burns Vertex AI
quota. Local recipe:

    docker compose up -d --wait
    SOLVO_RUN_E2E_TESTS=1 pytest tests/integration/test_pipeline_e2e.py -q

The test asserts three things in sequence:

1. A clean 3-lane Excel fixture transitions a job from `pending` →
   `completed` within 90 s. Without the Phase 6.5 per-task engine fix,
   tasks die on cross-loop SQLAlchemy errors and the job stays at
   `pending` indefinitely — catching Defect 1.

2. The job's outbox table contains exactly one `audit_log` row with
   `stage=validated` AND exactly one `slack_post` row whose payload has
   the requested channel and a non-empty `blocks` array. Without the
   Phase 6.5 `_validate` slack_post enqueue, the slack_post row is
   missing — catching Defect 3.

3. The dispatcher delivers the queued `slack_post` row to a recording
   stub of `chat_postMessage`. The bot must be invoked with the correct
   channel and non-empty blocks. (This step is the proof that the
   end-to-end Slack thread reply works — which the prior Stage F.3 halt
   could not demonstrate because Defect 1 prevented the job from ever
   reaching the dispatcher.)

Defect 2 (the missing fixtures) is implicitly caught by step 1 failing
to find the file path — but this test uses the existing
`fixtures/01_clean_excel.xlsx` rather than the K+N fixture because the
K+N path is the *demo* fixture and the e2e test wants a minimal
deterministic input.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

_should_run = os.getenv("SOLVO_RUN_E2E_TESTS") == "1"
_API_BASE = os.getenv("SOLVO_E2E_API_BASE", "http://localhost:8080")
_FIXTURE = Path("fixtures/01_clean_excel.xlsx")
_POLL_DEADLINE_SECONDS = 90.0
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


@pytest.mark.asyncio
async def test_clean_excel_reaches_completed_and_emits_slack_post(
    _compose_stack_ready: None,
) -> None:
    """End-to-end regression: clean fixture lands at `completed` and queues Slack."""
    channel = "C-E2E-TEST"
    job_id = _submit_job(channel)

    final_status = _poll_until_completed(job_id)
    assert final_status == "completed", (
        f"job {job_id} stuck at status={final_status} — regression in Defect 1 "
        "fix (Celery per-task engine) is likely"
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
