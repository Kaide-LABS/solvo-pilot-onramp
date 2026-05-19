"""GET /v1/jobs/{id}/status + /result tests. PHASE_2_SPEC §8 criteria 5 + 6."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routes import jobs as jobs_routes
from packages.core.db.session import get_async_session
from packages.core.models.ratesheet import JobStatus, NormalizedRatesheet


async def _fake_session_dep() -> AsyncIterator[Any]:
    yield object()


def _sample_payload(job_id: str = "j1") -> NormalizedRatesheet:
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
    return NormalizedRatesheet.model_validate(
        {
            "job_id": job_id,
            "prospect_id": "p123",
            "extraction_metadata": {
                "extractor_model": "gemini-3-flash-preview",
                "extracted_at": "2026-05-19T12:00:00+00:00",
                "prompt_version": "stage2.excel.v1",
                "cell_count": 5,
            },
            "lanes": [lane],
        }
    )


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(jobs_routes.router, prefix="/v1/jobs")
    app.dependency_overrides[get_async_session] = _fake_session_dep

    state: dict[str, Any] = {
        "statuses": {},
        "outputs": {},
    }

    async def fake_status(_session: Any, job_id: str) -> JobStatus | None:
        return state["statuses"].get(job_id)

    async def fake_output(_session: Any, job_id: str) -> NormalizedRatesheet | None:
        return state["outputs"].get(job_id)

    monkeypatch.setattr(jobs_routes, "get_job_status", fake_status)
    monkeypatch.setattr(jobs_routes, "get_output", fake_output)
    client = TestClient(app)
    client.state = state  # type: ignore[attr-defined]
    return client


def test_status_lookup_200(app: TestClient) -> None:
    """Known job returns 200 with the JobStatus shape."""
    app.state["statuses"]["j1"] = JobStatus(  # type: ignore[attr-defined]
        job_id="j1",
        status="pending",
        created_at=datetime.now(UTC),
    )
    resp = app.get("/v1/jobs/j1/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_status_lookup_404(app: TestClient) -> None:
    """Unknown job returns 404."""
    resp = app.get("/v1/jobs/missing/status")
    assert resp.status_code == 404


def test_result_returns_completed_payload(app: TestClient) -> None:
    """After a synthetic transition to completed, /result returns the persisted payload."""
    payload = _sample_payload("j1")
    app.state["statuses"]["j1"] = JobStatus(  # type: ignore[attr-defined]
        job_id="j1",
        status="completed",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        lane_count=1,
    )
    app.state["outputs"]["j1"] = payload  # type: ignore[attr-defined]
    resp = app.get("/v1/jobs/j1/result")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "j1"
    assert body["lanes"][0]["origin_port"]["code"] == "NLRTM"
    assert body["schema_version"] == "onramp.v1"


def test_result_404_when_unknown(app: TestClient) -> None:
    resp = app.get("/v1/jobs/missing/result")
    assert resp.status_code == 404


def test_result_409_when_not_completed(app: TestClient) -> None:
    app.state["statuses"]["j1"] = JobStatus(  # type: ignore[attr-defined]
        job_id="j1",
        status="extracting",
        created_at=datetime.now(UTC),
    )
    resp = app.get("/v1/jobs/j1/result")
    assert resp.status_code == 409
