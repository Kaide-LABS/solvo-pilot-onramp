"""pytest fixtures shared across the suite. See PHASE_1_SPEC §1 (tests block)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from packages.core.models.health import BootValidatorResult


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force Settings to load from a known minimal environment for every test.

    Clears any external pollution and seeds the variables Settings requires.
    """
    for k in (
        "ENVIRONMENT",
        "RELEASE_VERSION",
        "GCP_PROJECT_ID",
        "VERTEX_LOCATION",
        "POSTGRES_DSN_ASYNC",
        "POSTGRES_DSN_SYNC",
        "EXPECTED_ALEMBIC_HEAD",
        "REDIS_URL",
        "VERTEX_AI_ZDR_ENROLLED",
    ):
        monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west4")
    monkeypatch.setenv(
        "POSTGRES_DSN_ASYNC",
        "postgresql+asyncpg://onramp:onramp@localhost:5432/onramp",
    )
    monkeypatch.setenv(
        "POSTGRES_DSN_SYNC",
        "postgresql+psycopg2://onramp:onramp@localhost:5432/onramp",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("VERTEX_AI_ZDR_ENROLLED", "false")

    # Pydantic-settings caches via lru_cache in get_settings(); clear it.
    from packages.core.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    # Also reset env after the test so settings can't leak across boundaries.
    for k in ("GCP_PROJECT_ID", "VERTEX_LOCATION", "ENVIRONMENT"):
        if k in os.environ:
            del os.environ[k]


def make_validator_result(
    *,
    name: str = "vertex_ai_handshake",
    passed: bool = True,
    exit_code: int = 1,
    detail: str = "ok",
    latency_ms: int = 12,
) -> BootValidatorResult:
    """Construct a BootValidatorResult for assertions in unit tests."""
    return BootValidatorResult(
        validator_name=name,  # type: ignore[arg-type]
        passed=passed,
        exit_code_on_failure=exit_code,  # type: ignore[arg-type]
        latency_ms=latency_ms,
        detail=detail,
        checked_at=datetime.now(UTC),
    )
