"""Exception handlers. Implements PHASE_1_SPEC.md §4 (exceptions block)."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 for Pydantic strict-forbid violations.

    Phase 1 surface: lifespan-loaded models. Phase 2 reuses this handler for
    ingest-route bodies.
    """
    assert isinstance(exc, RequestValidationError | ValidationError)  # for type narrowing
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "detail": exc.errors(),
        },
    )


async def system_exit_handler(request: Request, exc: Exception) -> JSONResponse:
    """Defensive 503 if SystemExit ever escapes a request path.

    Should be unreachable in steady state — boot SystemExit halts the worker
    before any traffic arrives.
    """
    assert isinstance(exc, SystemExit)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "boot_failure", "exit_code": exc.code},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the handlers onto the FastAPI app."""
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(SystemExit, system_exit_handler)
