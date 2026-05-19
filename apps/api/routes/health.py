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


@router.get("/ready/cloudrun", response_model=HealthResponse)
async def cloudrun_readiness(request: Request) -> JSONResponse:
    """Cloud Run readiness — DB + Redis ping only (≤ 3 s budget).

    Implements PHASE_6_SPEC.md §4.1. Distinct from /v1/health/ready (which
    inspects the full four-validator boot result). Cloud Run's default probe
    deadline is aggressive; this lighter path avoids cold-start eviction.
    """
    import asyncio

    import redis.asyncio as redis_aio
    from sqlalchemy import text

    from packages.core.db.session import get_async_engine

    settings = get_settings()
    db_ok = False
    redis_ok = False

    async def _db_ping() -> bool:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    async def _redis_ping() -> bool:
        client: redis_aio.Redis = redis_aio.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url, decode_responses=True
        )
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()

    try:
        db_ok = await asyncio.wait_for(_db_ping(), timeout=0.5)
    except Exception:
        db_ok = False

    try:
        redis_ok = await asyncio.wait_for(_redis_ping(), timeout=0.5)
    except Exception:
        redis_ok = False

    healthy = db_ok and redis_ok
    body = HealthResponse(
        status="healthy" if healthy else "unhealthy",
        version=get_settings().release_version,
        region="europe-west4",
        timestamp=datetime.now(UTC),
        validators=request.app.state.boot_results,
    )
    code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body.model_dump(mode="json"))
