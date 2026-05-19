"""Cloud Run deploy smoke test. PHASE_6_SPEC §6.6 + §8 criterion 2.

Skipped automatically when SOLVO_DEPLOYED_URL is unset — the test requires
a live Cloud Run deployment and an identity token.

Run locally with:
    SOLVO_DEPLOYED_URL=https://solvo-onramp-api-xxx.run.app \
    SOLVO_ID_TOKEN="$(gcloud auth print-identity-token)" \
    pytest tests/integration/test_cloud_run_smoke.py -q
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

_url = os.getenv("SOLVO_DEPLOYED_URL")
_token = os.getenv("SOLVO_ID_TOKEN")
_should_run = bool(_url and _token)


@pytest.mark.skipif(not _should_run, reason="set SOLVO_DEPLOYED_URL + SOLVO_ID_TOKEN to enable")
def test_health_returns_healthy() -> None:
    """GET /v1/health → 200 + status=healthy + region=europe-west4."""
    headers = {"Authorization": f"Bearer {_token}"}
    response = httpx.get(f"{_url}/v1/health", headers=headers, timeout=10.0)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["region"] == "europe-west4"


@pytest.mark.skipif(not _should_run, reason="set SOLVO_DEPLOYED_URL + SOLVO_ID_TOKEN to enable")
def test_cloudrun_readiness_returns_within_three_seconds() -> None:
    """GET /v1/health/ready/cloudrun completes in ≤ 3 s and returns 200."""
    headers = {"Authorization": f"Bearer {_token}"}
    start = time.monotonic()
    response = httpx.get(f"{_url}/v1/health/ready/cloudrun", headers=headers, timeout=3.0)
    duration = time.monotonic() - start
    assert response.status_code == 200
    assert duration < 3.0


@pytest.mark.skipif(not _should_run, reason="set SOLVO_DEPLOYED_URL + SOLVO_ID_TOKEN to enable")
def test_audit_route_rejects_without_bearer() -> None:
    """GET /internal/v1/audit/<job> with the GCP id-token but no admin bearer → 403."""
    headers = {"Authorization": f"Bearer {_token}"}
    response = httpx.get(f"{_url}/internal/v1/audit/nonexistent", headers=headers, timeout=10.0)
    assert response.status_code == 403
