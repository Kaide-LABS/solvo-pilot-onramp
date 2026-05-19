"""structlog configuration. Implements PHASE_1_SPEC.md §1 (logging module)."""

from __future__ import annotations

import logging
import sys

import structlog

from packages.core.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog with JSON output in production, console in development.

    Idempotent — calling more than once replaces the previous configuration.
    """
    log_level = logging.INFO if settings.environment != "development" else logging.DEBUG

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
