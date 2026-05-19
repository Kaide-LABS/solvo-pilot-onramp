"""FastAPI app instance and lifespan handler. Implements PHASE_1_SPEC.md §4."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.exceptions import register_exception_handlers
from apps.api.routes import health as health_routes
from packages.compliance.boot_validators import run_all_boot_validators
from packages.core.logging import configure_logging
from packages.core.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run all four boot validators on startup.

    If any validator fails, raise SystemExit with that validator's exit code.
    Cloud Run interprets the non-zero exit as a health-check failure and the
    container never enters traffic rotation.
    """
    settings = get_settings()
    configure_logging(settings)
    results = await run_all_boot_validators(settings)
    app.state.boot_results = results
    failed = [r for r in results if not r.passed]
    if failed:
        raise SystemExit(failed[0].exit_code_on_failure)
    yield
    # Phase 1 shutdown: nothing. Phase 5 adds Slack client teardown.


_settings = get_settings()

app = FastAPI(
    title="Solvo Pilot Onramp — API",
    version=_settings.release_version,
    lifespan=lifespan,
    docs_url=None if _settings.environment == "production" else "/docs",
    redoc_url=None,
)
register_exception_handlers(app)
app.include_router(health_routes.router, prefix="/v1/health", tags=["health"])
