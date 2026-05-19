"""Transactional outbox invariant. PHASE_2_SPEC §8 criterion 7.

The function under test MUST NOT call session.commit(); the side-effect insert
has to be part of the caller's transaction. We assert the contract two ways:

1. enqueue_outbox_event issues exactly one INSERT against onramp_outbox and
   never calls session.commit() on its own.
2. When the caller's transaction is rolled back before commit, neither the
   simulated output insert nor the outbox insert is observed downstream
   (because no commit ever fired) — modeled via an in-memory transaction-state
   tracker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from packages.core.db.base import OnrampOutbox
from packages.ingest.outbox import enqueue_outbox_event


@pytest.mark.asyncio
async def test_enqueue_does_not_commit() -> None:
    """enqueue_outbox_event calls session.execute exactly once and never session.commit."""
    session = AsyncMock()
    await enqueue_outbox_event(
        session,
        job_id="j1",
        event_type="audit_log",
        payload={"stage": "extracted", "lane_count": 3},
    )
    assert session.execute.await_count == 1
    assert session.commit.await_count == 0
    insert_stmt = session.execute.await_args.args[0]
    assert insert_stmt.table.name == OnrampOutbox.__table__.name
    params = insert_stmt.compile().params
    assert params["job_id"] == "j1"
    assert params["event_type"] == "audit_log"
    assert params["payload"] == {"stage": "extracted", "lane_count": 3}


@dataclass
class _TxnLog:
    """Tracks pending-but-uncommitted INSERTs and what eventually committed."""

    pending: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    committed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    rolled_back: bool = False


class _TxnSession:
    """Minimal AsyncSession stand-in that models commit/rollback atomicity."""

    def __init__(self, log: _TxnLog) -> None:
        self._log = log

    async def execute(self, stmt: Any) -> None:
        table_name = stmt.table.name
        self._log.pending.append((table_name, dict(stmt.compile().params)))

    async def commit(self) -> None:
        self._log.committed.extend(self._log.pending)
        self._log.pending.clear()

    async def rollback(self) -> None:
        self._log.rolled_back = True
        self._log.pending.clear()


@pytest.mark.asyncio
async def test_rollback_drops_outbox_and_output_together() -> None:
    """Rollback before commit ⇒ neither the output insert nor the outbox insert lands."""
    from sqlalchemy import insert as sa_insert

    from packages.core.db.base import OnrampOutput

    log = _TxnLog()
    session = _TxnSession(log)

    # Simulate the production write pattern: output insert + outbox enqueue.
    await session.execute(
        sa_insert(OnrampOutput).values(
            job_id="j1",
            normalized_payload={"lanes": []},
            lane_count=0,
            flagged_count=0,
            rejected_count=0,
        )
    )
    await enqueue_outbox_event(
        session, job_id="j1", event_type="audit_log", payload={"stage": "extracted"}
    )
    # Deliberately abandon the transaction.
    await session.rollback()

    assert log.rolled_back is True
    assert log.committed == []
    assert log.pending == []


@pytest.mark.asyncio
async def test_commit_lands_both_inserts_atomically() -> None:
    """Commit ⇒ both the output insert and the outbox enqueue are flushed together."""
    from sqlalchemy import insert as sa_insert

    from packages.core.db.base import OnrampOutput

    log = _TxnLog()
    session = _TxnSession(log)

    await session.execute(
        sa_insert(OnrampOutput).values(
            job_id="j1",
            normalized_payload={"lanes": []},
            lane_count=0,
            flagged_count=0,
            rejected_count=0,
        )
    )
    await enqueue_outbox_event(
        session, job_id="j1", event_type="audit_log", payload={"stage": "extracted"}
    )
    await session.commit()

    committed_tables = [name for name, _ in log.committed]
    assert committed_tables == ["onramp_outputs", "onramp_outbox"]
