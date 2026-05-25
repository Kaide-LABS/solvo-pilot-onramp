"""Outbox drain worker. Implements PHASE_5_SPEC.md §6.4.

Hard requirements (PHASE_5_SPEC §6.4):
  - Redis lock pattern: SET key value NX EX seconds (NOT Redlock, NOT WATCH/MULTI).
  - Exponential backoff: 5s → 30s → 5m → 30m → 2h → 24h, then stop at attempts ≥ 6.
  - At-least-once delivery; per-event-type idempotency in delivery.py.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import redis.asyncio as redis_aio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.worker.celery_app import celery_app
from packages.core.db.base import OnrampOutbox
from packages.core.db.session import make_async_engine
from packages.core.settings import Settings, get_settings
from packages.dispatcher.delivery import (
    deliver_access_log,
    deliver_audit_log,
    deliver_signed_url_create,
    deliver_slack_post,
    deliver_upload_result,
    deliver_webhook_callback,
)

_log = logging.getLogger(__name__)

# Exponential backoff. Index = attempts (0-based). Beyond 6 attempts the
# dispatcher gives up and leaves the row with delivered_at=NULL,
# next_retry_at=NULL — alerting picks it up via the dashboard.
BACKOFF_SCHEDULE_SECONDS: Final[tuple[int, ...]] = (5, 30, 300, 1800, 7200, 86400)
MAX_ATTEMPTS: Final[int] = len(BACKOFF_SCHEDULE_SECONDS)
LOCK_TTL_SECONDS: Final[int] = 30
BATCH_SIZE: Final[int] = 50


async def _acquire_lock(client: redis_aio.Redis, outbox_id: int, worker_uuid: str) -> bool:
    """Acquire the dispatcher's per-row lock via SET NX EX."""
    key = f"solvo:onramp:outbox:{outbox_id}"
    result = await client.set(key, worker_uuid, nx=True, ex=LOCK_TTL_SECONDS)
    return bool(result)


async def _dispatch_one(payload: dict[str, Any], event_type: str, settings: Settings) -> None:
    """Invoke the per-event-type delivery handler."""
    if event_type == "slack_post":
        await deliver_slack_post(payload, settings)
    elif event_type == "webhook_callback":
        await deliver_webhook_callback(payload, settings)
    elif event_type == "signed_url_create":
        await deliver_signed_url_create(payload, settings)
    elif event_type == "upload_result":
        await deliver_upload_result(payload, settings)
    elif event_type == "audit_log":
        await deliver_audit_log(payload, settings)
    elif event_type == "access_log":
        await deliver_access_log(payload, settings)
    else:
        raise ValueError(f"unknown outbox event_type: {event_type!r}")


def backoff_for(attempts: int) -> int | None:
    """Return the next-retry delay in seconds, or None when over MAX_ATTEMPTS."""
    if attempts < 0 or attempts >= MAX_ATTEMPTS:
        return None
    return BACKOFF_SCHEDULE_SECONDS[attempts]


async def _drain_once(settings: Settings) -> dict[str, int]:
    """Drain at most BATCH_SIZE undelivered outbox rows. Returns a counter dict.

    Phase 6.5 (§6.1): owns its own AsyncEngine for this beat tick and disposes
    it in the `finally`. The dispatcher beat fires every 5 s, each tick
    running under a fresh `asyncio.run` loop, so the engine cannot be cached.
    """
    engine = make_async_engine(settings)
    redis_client: redis_aio.Redis = redis_aio.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, decode_responses=True
    )
    worker_uuid = uuid.uuid4().hex
    delivered = 0
    failed = 0
    skipped = 0

    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session, session.begin():
            now = datetime.now(UTC)
            stmt = (
                select(OnrampOutbox)
                .where(OnrampOutbox.delivered_at.is_(None))
                .where((OnrampOutbox.next_retry_at.is_(None)) | (OnrampOutbox.next_retry_at <= now))
                .limit(BATCH_SIZE)
            )
            rows = (await session.execute(stmt)).scalars().all()

        for row in rows:
            if not await _acquire_lock(redis_client, row.outbox_id, worker_uuid):
                skipped += 1
                continue
            try:
                await _dispatch_one(row.payload, row.event_type, settings)
                async with factory() as session, session.begin():
                    await session.execute(
                        update(OnrampOutbox)
                        .where(OnrampOutbox.outbox_id == row.outbox_id)
                        .values(delivered_at=datetime.now(UTC), next_retry_at=None)
                    )
                delivered += 1
            except Exception as exc:
                next_attempts = row.attempts + 1
                delay = backoff_for(next_attempts - 1)
                next_retry_at = (
                    datetime.now(UTC) + timedelta(seconds=delay) if delay is not None else None
                )
                async with factory() as session, session.begin():
                    await session.execute(
                        update(OnrampOutbox)
                        .where(OnrampOutbox.outbox_id == row.outbox_id)
                        .values(attempts=next_attempts, next_retry_at=next_retry_at)
                    )
                failed += 1
                _log.warning(
                    "dispatch outbox_id=%s event=%s attempt=%d failed: %s",
                    row.outbox_id,
                    row.event_type,
                    next_attempts,
                    exc,
                )
    finally:
        await redis_client.aclose()
        await engine.dispose()

    return {"delivered": delivered, "failed": failed, "skipped": skipped}


@celery_app.task(name="tasks.dispatcher.drain_outbox", bind=True, max_retries=0)
def drain_outbox_task(self: Any) -> dict[str, int]:
    """Celery-beat-driven outbox drain. Runs every 5 seconds per beat schedule."""
    return asyncio.run(_drain_once(get_settings()))
