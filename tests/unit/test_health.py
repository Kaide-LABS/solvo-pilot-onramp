"""/v1/health route tests. PHASE_1_SPEC §9 criterion 8."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_validator_result


def _build_app(monkeypatch: pytest.MonkeyPatch, results: list[Any]) -> TestClient:
    """Construct an app whose lifespan is patched to inject canned validator results."""
    from apps.api import main as main_module

    async def _fake_run(_settings: Any) -> list[Any]:
        return results

    monkeypatch.setattr(main_module, "run_all_boot_validators", _fake_run)
    # Re-build the app so the patched function is picked up by the lifespan.
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    from apps.api.exceptions import register_exception_handlers
    from apps.api.routes import health as health_routes
    from packages.core.logging import configure_logging
    from packages.core.settings import get_settings

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(get_settings())
        app.state.boot_results = await _fake_run(get_settings())
        failed = [r for r in app.state.boot_results if not r.passed]
        if failed:
            raise SystemExit(failed[0].exit_code_on_failure)
        yield

    app = FastAPI(lifespan=_lifespan)
    register_exception_handlers(app)
    app.include_router(health_routes.router, prefix="/v1/health")
    return TestClient(app)


def test_health_all_pass_returns_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """All four validators pass → /v1/health returns 200 status=healthy."""
    results = [
        make_validator_result(name="vertex_ai_handshake", exit_code=1),
        make_validator_result(name="postgres_alembic_head", exit_code=2),
        make_validator_result(name="un_locode_table_integrity", exit_code=3),
        make_validator_result(name="vertex_ai_compliance_handshake", exit_code=4),
    ]
    with _build_app(monkeypatch, results) as client:
        resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["region"] == "europe-west4"
    assert len(body["validators"]) == 4


async def _run_lifespan(monkeypatch: pytest.MonkeyPatch, results: list[Any]) -> None:
    """Drive the production lifespan directly, asserting its SystemExit behavior.

    Going through TestClient swallows BaseExceptions; the lifespan is a regular
    async context manager so we exercise it without the ASGI wrapper.
    """
    from fastapi import FastAPI

    from apps.api import main as main_module

    async def _fake_run(_settings: Any) -> list[Any]:
        return results

    monkeypatch.setattr(main_module, "run_all_boot_validators", _fake_run)
    app = FastAPI()
    async with main_module.lifespan(app):
        pass


@pytest.mark.asyncio
async def test_readiness_single_fail_raises_systemexit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single validator fail triggers SystemExit with that validator's exit code."""
    failing = make_validator_result(
        name="vertex_ai_compliance_handshake",
        passed=False,
        exit_code=4,
        detail="ZDR not enrolled",
    )
    with pytest.raises(SystemExit) as caught:
        await _run_lifespan(monkeypatch, [failing])
    assert caught.value.code == 4


def test_readiness_503_via_request_state() -> None:
    """When validators have failed, /ready returns 503 (state-injected — no lifespan)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from apps.api.routes import health as health_routes

    app = FastAPI()
    app.include_router(health_routes.router, prefix="/v1/health")
    app.state.boot_results = [
        make_validator_result(
            name="vertex_ai_compliance_handshake",
            passed=False,
            exit_code=4,
            detail="forced",
        )
    ]
    with TestClient(app) as client:
        resp = client.get("/v1/health/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_multi_fail_first_failure_dictates_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple validators fail, the first failure's exit code wins (per §6.1)."""
    results = [
        make_validator_result(name="vertex_ai_handshake", passed=False, exit_code=1, detail="x"),
        make_validator_result(
            name="postgres_alembic_head", passed=False, exit_code=2, detail="y"
        ),
        make_validator_result(
            name="un_locode_table_integrity", passed=True, exit_code=3, detail="z"
        ),
        make_validator_result(
            name="vertex_ai_compliance_handshake", passed=False, exit_code=4, detail="w"
        ),
    ]
    with pytest.raises(SystemExit) as caught:
        await _run_lifespan(monkeypatch, results)
    assert caught.value.code == 1
