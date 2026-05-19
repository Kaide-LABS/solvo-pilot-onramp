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

# Phase 2 registers tasks.ingest.*; Phase 5 adds packages.dispatcher.
celery_app.autodiscover_tasks(
    packages=["packages.ingest", "packages.dispatcher"],
    related_name="outbox_worker",
)
celery_app.autodiscover_tasks(packages=["packages.ingest"], related_name="tasks")

# Phase 5: drain the outbox every 5 seconds.
celery_app.conf.beat_schedule = {
    "drain-outbox-every-5s": {
        "task": "tasks.dispatcher.drain_outbox",
        "schedule": 5.0,
    },
}
