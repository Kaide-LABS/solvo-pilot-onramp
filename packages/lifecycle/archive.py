"""90-day archive job. Implements PHASE_6_SPEC.md §6.3.

Runs as a Celery task on a daily beat schedule. Selects onramp_outputs rows
older than the configured age, gzip-encodes the normalized_payload JSON,
uploads to gs://{gcs_archive_bucket}/jobs/{job_id}.json.gz, then DELETEs the
row. Idempotent — already-archived rows are skipped.

onramp_audit_log is NEVER archived: §3.10.3 sets a 365-day floor for audit
retention, well above any archive horizon. Audit rows live forever in
Postgres (or move to Cloud SQL backup on a separate ops cadence).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker.celery_app import celery_app
from packages.core.db.base import OnrampJob, OnrampOutput
from packages.core.db.session import get_async_engine
from packages.core.models.lifecycle import ArchiveCandidate
from packages.core.settings import Settings, get_settings
from packages.storage.upload import upload_blob

_log = logging.getLogger(__name__)


def _blob_name(job_id: str) -> str:
    return f"jobs/{job_id}.json.gz"


async def _select_candidates(
    session: AsyncSession, age_days: int
) -> list[tuple[str, datetime, dict[str, Any]]]:
    """Return (job_id, completed_at, normalized_payload) tuples older than age_days."""
    cutoff = datetime.now(UTC) - timedelta(days=age_days)
    result = await session.execute(
        select(OnrampJob.job_id, OnrampJob.completed_at, OnrampOutput.normalized_payload)
        .join(OnrampOutput, OnrampOutput.job_id == OnrampJob.job_id)
        .where(OnrampJob.status == "completed")
        .where(OnrampJob.completed_at.is_not(None))
        .where(OnrampJob.completed_at < cutoff)
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


async def archive_completed_jobs(
    *,
    age_days: int,
    settings: Settings,
) -> list[ArchiveCandidate]:
    """Archive onramp_outputs rows older than `age_days` to GCS, then delete them.

    Returns the list of ArchiveCandidate rows that were archived this run.
    The audit_log row (`stage="archived"`) is written by the caller; this
    function returns the candidate list so the caller can compose its own
    transactional audit event.
    """
    factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)
    candidates: list[ArchiveCandidate] = []

    async with factory() as session:
        rows = await _select_candidates(session, age_days)

    for job_id, completed_at, payload in rows:
        blob_name = _blob_name(job_id)
        gzipped = gzip.compress(json.dumps(payload).encode("utf-8"))
        try:
            await upload_blob(
                bucket=settings.gcs_archive_bucket,
                blob_name=blob_name,
                payload=gzipped,
                content_type="application/gzip",
            )
        except Exception as exc:
            _log.warning("archive: upload failed for %s: %s", job_id, exc)
            continue

        async with factory() as session, session.begin():
            await session.execute(delete(OnrampOutput).where(OnrampOutput.job_id == job_id))

        candidates.append(
            ArchiveCandidate(
                job_id=job_id,
                completed_at=completed_at,
                archive_blob_name=blob_name,
                source_table="onramp_outputs",
            )
        )

    _log.info("archive: archived %d jobs (age_days=%d)", len(candidates), age_days)
    return candidates


@celery_app.task(name="tasks.lifecycle.archive_old", bind=True, max_retries=0)
def archive_old_task(self: Any) -> dict[str, int]:
    """Beat-scheduled archive sweep. Returns a counter dict."""
    settings = get_settings()
    candidates = asyncio.run(
        archive_completed_jobs(age_days=settings.archive_age_days, settings=settings)
    )
    return {"archived": len(candidates)}
