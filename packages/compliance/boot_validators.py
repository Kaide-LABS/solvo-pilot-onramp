"""Container-boot validators. Implements PHASE_1_SPEC.md §6.

Four validators run in sequence inside the FastAPI lifespan handler.
The first failure dictates the exit code per ULTIMATE_PRD §3.7 + §3.10.5.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from packages.compliance.retention import (
    assert_request_response_logging_disabled,
    disable_request_response_logging,
)
from packages.compliance.vertex_client import get_vertex_client
from packages.core.models.health import BootValidatorResult
from packages.core.settings import Settings

_log = logging.getLogger(__name__)

ValidatorName = Literal[
    "vertex_ai_handshake",
    "postgres_alembic_head",
    "un_locode_table_integrity",
    "vertex_ai_compliance_handshake",
]
ExitCode = Literal[1, 2, 3, 4]


async def _run_one(
    name: ValidatorName,
    exit_code: ExitCode,
    coro_factory: Callable[[], Awaitable[str]],
    timeout_seconds: float,
) -> BootValidatorResult:
    """Run a single validator coroutine with a wall-clock budget.

    coro_factory returns a coroutine that resolves to a detail string on
    success or raises an exception on failure. The detail string MUST NOT
    contain PII; only diagnostic identifiers.
    """
    started = time.monotonic()
    try:
        detail = await asyncio.wait_for(coro_factory(), timeout=timeout_seconds)
        passed = True
    except Exception as exc:  # broad by design — boot-time triage
        detail = f"{type(exc).__name__}: {str(exc)[:400]}"
        passed = False
        _log.warning("boot validator %s failed: %s", name, detail)
    latency_ms = int((time.monotonic() - started) * 1000)
    return BootValidatorResult(
        validator_name=name,
        passed=passed,
        exit_code_on_failure=exit_code,
        latency_ms=latency_ms,
        detail=detail,
        checked_at=datetime.now(UTC),
    )


async def _validate_vertex_handshake(settings: Settings) -> BootValidatorResult:
    """Validator 1 — Vertex AI Gemini flash ping. Exit code 1."""

    async def _do() -> str:
        client = get_vertex_client(settings)
        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
            contents="ping",
        )
        if not getattr(response, "candidates", None):
            raise AssertionError("no candidates returned from gemini-3-flash-preview")
        return f"flash_preview_responsive in {settings.vertex_location}"

    return await _run_one(
        name="vertex_ai_handshake",
        exit_code=1,
        coro_factory=_do,
        timeout_seconds=5.0,
    )


async def _validate_postgres_alembic_head(settings: Settings) -> BootValidatorResult:
    """Validator 2 — Postgres reachable and migration head matches expectation. Exit code 2."""

    async def _do() -> str:
        engine = create_async_engine(settings.postgres_dsn_async, poolclass=None)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.first()
                if row is None:
                    raise AssertionError("alembic_version table empty")
                if row[0] != settings.expected_alembic_head:
                    raise AssertionError(
                        f"alembic head mismatch: db={row[0]} expected={settings.expected_alembic_head}"
                    )
                return f"alembic_head={row[0]}"
        finally:
            await engine.dispose()

    return await _run_one(
        name="postgres_alembic_head",
        exit_code=2,
        coro_factory=_do,
        timeout_seconds=5.0,
    )


async def _validate_un_locode_table_integrity(settings: Settings) -> BootValidatorResult:
    """Validator 3 — UN/LOCODE reference table row count. Exit code 3.

    Phase 1 short-circuit: the un_locode_reference table does not yet exist.
    When absent, the validator returns passed=True with a "phase1 short-circuit"
    detail. Phase 3 replaces this short-circuit with the real >= 100_000 check.
    """

    async def _do() -> str:
        engine = create_async_engine(settings.postgres_dsn_async, poolclass=None)
        try:
            async with engine.connect() as conn:
                exists = (
                    await conn.execute(
                        text(
                            "SELECT 1 FROM information_schema.tables "
                            "WHERE table_name = 'un_locode_reference'"
                        )
                    )
                ).first()
                if exists is None:
                    return "table_absent_phase1_short_circuit"
                result = await conn.execute(text("SELECT count(*) FROM un_locode_reference"))
                count = int(result.scalar() or 0)
                if count < 100_000:
                    raise AssertionError(f"UN/LOCODE row count {count} < 100000")
                return f"un_locode_rows={count}"
        finally:
            await engine.dispose()

    return await _run_one(
        name="un_locode_table_integrity",
        exit_code=3,
        coro_factory=_do,
        timeout_seconds=5.0,
    )


async def _validate_vertex_compliance(settings: Settings) -> BootValidatorResult:
    """Validator 4 — §3.10.5 Vertex AI compliance handshake. Exit code 4.

    Confirms project-level zero-retention state by:
    1. Calling set_request_response_logging_config(enabled=False) on each
       Gemini publisher model in scope (idempotent).
    2. Reading the configuration back and asserting it is disabled.
    3. In production, requiring VERTEX_AI_ZDR_ENROLLED to be true (the ops
       checklist in docs/compliance_setup.md owns this env var).
    """

    async def _do() -> str:
        models_in_scope = ["gemini-3-flash-preview", "gemini-3.1-pro-preview"]
        for model_id in models_in_scope:
            await disable_request_response_logging(settings, model_id)
            await assert_request_response_logging_disabled(settings, model_id)
        if settings.environment == "production" and not settings.vertex_ai_zdr_enrolled:
            raise AssertionError(
                "ZDR program not enrolled — required for production compliance posture"
            )
        return (
            f"rrl_disabled=True zdr_enrolled={settings.vertex_ai_zdr_enrolled} "
            f"models={','.join(m.split('-', 1)[1] for m in models_in_scope)}"
        )

    return await _run_one(
        name="vertex_ai_compliance_handshake",
        exit_code=4,
        coro_factory=_do,
        timeout_seconds=8.0,
    )


async def run_all_boot_validators(settings: Settings) -> list[BootValidatorResult]:
    """Run all four boot validators in sequence and return their results.

    Order matters: handshake → schema → reference data → compliance. The
    caller is responsible for inspecting the results and triggering SystemExit
    with the first failure's exit code, per PHASE_1_SPEC §4.
    """
    return [
        await _validate_vertex_handshake(settings),
        await _validate_postgres_alembic_head(settings),
        await _validate_un_locode_table_integrity(settings),
        await _validate_vertex_compliance(settings),
    ]


# Re-export for test seams.
__all__ = [
    "BootValidatorResult",
    "ExitCode",
    "ValidatorName",
    "run_all_boot_validators",
    cast(str, _validate_postgres_alembic_head.__name__),
    cast(str, _validate_un_locode_table_integrity.__name__),
    cast(str, _validate_vertex_compliance.__name__),
    cast(str, _validate_vertex_handshake.__name__),
]
