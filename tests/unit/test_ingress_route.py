"""POST /v1/ingest/ratesheet tests. PHASE_2_SPEC §8 criteria 3 + 4."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routes import ingest as ingest_routes
from packages.core.db.session import get_async_session
from packages.core.models.ratesheet import JobStatus

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "01_clean_excel.xlsx"


class _FakeSession:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


async def _fake_session_dep() -> AsyncIterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a minimal app exposing only the ingest router with mocked repo + queue."""
    app = FastAPI()
    app.include_router(ingest_routes.router, prefix="/v1/ingest/ratesheet")
    app.dependency_overrides[get_async_session] = _fake_session_dep

    state: dict[str, Any] = {"jobs": {}, "enqueued": []}

    async def fake_insert(_session: Any, **kw: Any) -> tuple[str, bool]:
        if kw["input_hash"] in state["jobs"]:
            return state["jobs"][kw["input_hash"]], False
        state["jobs"][kw["input_hash"]] = kw["job_id"]
        return kw["job_id"], True

    async def fake_status(_session: Any, job_id: str) -> JobStatus | None:
        if job_id not in state["jobs"].values():
            return None
        return JobStatus(
            job_id=job_id,
            status="pending",
            created_at=datetime.now(UTC),
            completed_at=None,
            lane_count=None,
        )

    def fake_enqueue(job_id: str, staging_path: str) -> None:
        state["enqueued"].append((job_id, staging_path))

    monkeypatch.setattr(ingest_routes, "insert_job_if_new", fake_insert)
    monkeypatch.setattr(ingest_routes, "get_job_status", fake_status)
    monkeypatch.setattr(ingest_routes, "_enqueue_classify", fake_enqueue)
    client = TestClient(app)
    client.state = state  # type: ignore[attr-defined]
    return client


def _post_fixture(client: TestClient, *, hint: str = "auto") -> Any:
    return client.post(
        "/v1/ingest/ratesheet",
        files={"upload": ("01.xlsx", FIXTURE.read_bytes(), "application/vnd.openxmlformats")},
        data={
            "prospect_id": "p123",
            "prospect_name": "Acme Forwarding",
            "source_format_hint": hint,
            "requesting_user_slack_id": "U123",
            "callback_channel": "#freight",
        },
    )


def test_happy_path_returns_202_and_enqueues(app: TestClient) -> None:
    """First post returns 202 with a JobStatus body and triggers one Celery enqueue."""
    resp = _post_fixture(app)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["job_id"]
    assert len(app.state["enqueued"]) == 1  # type: ignore[attr-defined]


def test_duplicate_input_hash_returns_409(app: TestClient) -> None:
    """Reposting the same bytes returns 409 with the existing job_id."""
    first = _post_fixture(app)
    assert first.status_code == 202
    first_id = first.json()["job_id"]
    second = _post_fixture(app)
    assert second.status_code == 409
    detail = second.json()
    assert detail["error"] == "duplicate_input_hash"
    assert detail["job"]["job_id"] == first_id
    # Only one enqueue happened, even though we posted twice.
    assert len(app.state["enqueued"]) == 1  # type: ignore[attr-defined]


def test_missing_form_field_returns_422(app: TestClient) -> None:
    """Omitting a required form field is rejected by FastAPI / Pydantic."""
    resp = app.post(
        "/v1/ingest/ratesheet",
        files={"upload": ("01.xlsx", FIXTURE.read_bytes())},
        data={"prospect_id": "p123"},
    )
    assert resp.status_code == 422


def test_oversized_upload_returns_422(app: TestClient) -> None:
    """An upload over the 25 MiB cap is rejected before hashing."""
    big = io.BytesIO(b"x" * (25 * 1024 * 1024 + 1))
    resp = app.post(
        "/v1/ingest/ratesheet",
        files={"upload": ("big.xlsx", big.getvalue())},
        data={
            "prospect_id": "p123",
            "prospect_name": "Acme",
            "source_format_hint": "auto",
            "requesting_user_slack_id": "U1",
            "callback_channel": "#x",
        },
    )
    assert resp.status_code == 422
