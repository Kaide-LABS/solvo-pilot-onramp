"""Transactional outbox enqueue helper. Implements PHASE_2_SPEC.md §6.4.

The caller owns the transaction. enqueue_outbox_event MUST NOT call
session.commit() — committing here would split the side-effect insert from
the job-state update and break the load-bearing outbox invariant.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import OnrampOutbox

OutboxEventType = Literal[
    "slack_post",
    "webhook_callback",
    "audit_log",
    "signed_url_create",
    "access_log",
]


async def enqueue_outbox_event(
    session: AsyncSession,
    *,
    job_id: str,
    event_type: OutboxEventType,
    payload: dict[str, Any],
) -> None:
    """Insert a row into onramp_outbox within the caller's transaction.

    Idempotency is left to the caller's transactional context — the outbox
    table has no uniqueness constraint on (job_id, event_type), because some
    event types (audit_log, slack_post retries) legitimately repeat per job.
    The caller is responsible for issuing this insert exactly once per
    business-logic event.
    """
    await session.execute(
        insert(OnrampOutbox).values(
            job_id=job_id,
            event_type=event_type,
            payload=payload,
        )
    )
