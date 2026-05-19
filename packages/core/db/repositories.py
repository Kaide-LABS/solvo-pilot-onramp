"""Async CRUD on Phase 2 tables. Implements PHASE_2_SPEC.md §1 (repositories.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import OnrampJob, OnrampOutput
from packages.core.models.ratesheet import JobStatus, NormalizedRatesheet


async def insert_job_if_new(
    session: AsyncSession,
    *,
    job_id: str,
    prospect_id: str,
    prospect_name: str,
    input_hash: str,
    source_format: str,
) -> tuple[str, bool]:
    """Insert a fresh job row, or return the existing job_id when input_hash collides.

    Returns (job_id, created). created=False means we found an existing row with
    the same input_hash — the caller should return HTTP 409 with that job_id.
    """
    stmt = (
        pg_insert(OnrampJob)
        .values(
            job_id=job_id,
            prospect_id=prospect_id,
            prospect_name=prospect_name,
            status="pending",
            input_hash=input_hash,
            source_format=source_format,
        )
        .on_conflict_do_nothing(index_elements=[OnrampJob.input_hash])
        .returning(OnrampJob.job_id)
    )
    result = await session.execute(stmt)
    returned = result.scalar()
    if returned is not None:
        return returned, True
    # Conflict — look up the existing job by input_hash.
    existing = await session.execute(
        select(OnrampJob.job_id).where(OnrampJob.input_hash == input_hash)
    )
    found = existing.scalar_one()
    return found, False


async def get_job(session: AsyncSession, job_id: str) -> OnrampJob | None:
    """Return the OnrampJob row or None."""
    result = await session.execute(select(OnrampJob).where(OnrampJob.job_id == job_id))
    return result.scalar_one_or_none()


async def get_job_status(session: AsyncSession, job_id: str) -> JobStatus | None:
    """Project an OnrampJob plus lane_count into the public JobStatus shape."""
    job = await get_job(session, job_id)
    if job is None:
        return None
    output = await session.execute(
        select(OnrampOutput.lane_count).where(OnrampOutput.job_id == job_id)
    )
    return JobStatus(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        created_at=job.created_at,
        completed_at=job.completed_at,
        lane_count=output.scalar(),
    )


async def update_job_status(
    session: AsyncSession,
    job_id: str,
    *,
    new_status: str,
    completed: bool = False,
) -> None:
    """Mutate onramp_jobs.status (and completed_at when completed=True)."""
    values: dict[str, Any] = {"status": new_status}
    if completed:
        values["completed_at"] = datetime.now(UTC)
    await session.execute(update(OnrampJob).where(OnrampJob.job_id == job_id).values(**values))


async def insert_output(
    session: AsyncSession,
    *,
    job_id: str,
    payload: NormalizedRatesheet,
) -> None:
    """Insert the normalized payload + counts into onramp_outputs."""
    await session.execute(
        pg_insert(OnrampOutput).values(
            job_id=job_id,
            normalized_payload=payload.model_dump(mode="json"),
            lane_count=len(payload.lanes),
            flagged_count=len(payload.flagged_for_review),
            rejected_count=len(payload.deterministically_rejected),
        )
    )


async def get_output(session: AsyncSession, job_id: str) -> NormalizedRatesheet | None:
    """Return the NormalizedRatesheet for a completed job, or None."""
    result = await session.execute(
        select(OnrampOutput.normalized_payload).where(OnrampOutput.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return NormalizedRatesheet.model_validate(row)
