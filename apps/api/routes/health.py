"""Health and readiness routes. Implements PHASE_1_SPEC.md §4."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from packages.core.models.health import BootValidatorResult, HealthResponse
from packages.core.settings import get_settings

router = APIRouter()


def _aggregate(results: list[BootValidatorResult]) -> HealthResponse:
    """Build a HealthResponse from a list of boot-validator results."""
    healthy = all(r.passed for r in results)
    return HealthResponse(
        status="healthy" if healthy else "unhealthy",
        version=get_settings().release_version,
        region="europe-west4",
        timestamp=datetime.now(UTC),
        validators=results,
    )


@router.get("", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health(request: Request) -> HealthResponse:
    """Liveness probe. Always 200; the status field reflects validator state.

    Cloud Run uses /v1/health/ready for traffic gating; this route stays 200
    so logs and diagnostics remain scrapable even when validators failed.
    """
    results: list[BootValidatorResult] = request.app.state.boot_results
    return _aggregate(results)


@router.get("/ready", response_model=HealthResponse)
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe. 503 if any validator failed; 200 otherwise."""
    results: list[BootValidatorResult] = request.app.state.boot_results
    body = _aggregate(results)
    code = status.HTTP_200_OK if body.status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body.model_dump(mode="json"))
