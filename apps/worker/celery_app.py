"""Celery instance for solvo-onramp-worker. Phase 1: no task definitions yet.

Implements PHASE_1_SPEC.md §8 (celery_app.py block).
"""

from __future__ import annotations

from celery import Celery

from apps.worker import boot  # noqa: F401  # registers worker_init handler
from packages.core.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "solvo-onramp",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Phase 1: no tasks registered. Phases 2–4 add them under packages.ingest.
