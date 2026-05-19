"""Audit route auth + 404 — PHASE_4_SPEC §8 criterion 7."""

from __future__ import annotations

import pytest

from apps.api.routes import audit as audit_route
from packages.core.settings import Settings


@pytest.mark.asyncio
async def test_require_internal_service_account_rejects_empty_token() -> None:
    """When internal_admin_token is empty, the dependency always raises 403."""
    settings = Settings(  # type: ignore[call-arg]
        gcp_project_id="x",
        postgres_dsn_async="postgresql+asyncpg://x@localhost/x",
        postgres_dsn_sync="postgresql+psycopg2://x@localhost/x",
        redis_url="redis://localhost",
        internal_admin_token="",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        await audit_route.require_internal_service_account(
            authorization="Bearer anything",
            settings=settings,
        )
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_require_internal_service_account_rejects_missing_header() -> None:
    """Missing Authorization header → 403."""
    settings = Settings(  # type: ignore[call-arg]
        gcp_project_id="x",
        postgres_dsn_async="postgresql+asyncpg://x@localhost/x",
        postgres_dsn_sync="postgresql+psycopg2://x@localhost/x",
        redis_url="redis://localhost",
        internal_admin_token="expected-token",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        await audit_route.require_internal_service_account(authorization=None, settings=settings)
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_require_internal_service_account_accepts_matching_bearer() -> None:
    """Matching Bearer token returns the configured principal."""
    settings = Settings(  # type: ignore[call-arg]
        gcp_project_id="x",
        postgres_dsn_async="postgresql+asyncpg://x@localhost/x",
        postgres_dsn_sync="postgresql+psycopg2://x@localhost/x",
        redis_url="redis://localhost",
        internal_admin_token="expected-token",
        internal_admin_principal="ops@kaide.so",
    )
    result = await audit_route.require_internal_service_account(
        authorization="Bearer expected-token",
        settings=settings,
    )
    assert result == "ops@kaide.so"


@pytest.mark.asyncio
async def test_require_internal_service_account_rejects_wrong_bearer() -> None:
    """Mismatched bearer → 403."""
    settings = Settings(  # type: ignore[call-arg]
        gcp_project_id="x",
        postgres_dsn_async="postgresql+asyncpg://x@localhost/x",
        postgres_dsn_sync="postgresql+psycopg2://x@localhost/x",
        redis_url="redis://localhost",
        internal_admin_token="expected-token",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        await audit_route.require_internal_service_account(
            authorization="Bearer wrong",
            settings=settings,
        )
    assert caught.value.status_code == 403
