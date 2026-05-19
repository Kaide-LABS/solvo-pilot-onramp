"""GET /v1/jobs/{id}/status and /v1/jobs/{id}/result. Implements PHASE_2_SPEC.md §4.2–§4.3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.repositories import get_job_status, get_output
from packages.core.db.session import get_async_session
from packages.core.models.ratesheet import JobStatus, NormalizedRatesheet

router = APIRouter()


@router.get(
    "/{job_id}/status",
    response_model=JobStatus,
    responses={404: {"description": "job_not_found"}},
)
async def job_status(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> JobStatus:
    """Return the public-facing job status row."""
    result = await get_job_status(session, job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return result


@router.get(
    "/{job_id}/result",
    response_model=NormalizedRatesheet,
    responses={
        404: {"description": "job_not_found"},
        409: {"description": "job_not_completed"},
    },
)
async def job_result(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> NormalizedRatesheet:
    """Return the persisted NormalizedRatesheet for a completed job."""
    status_row = await get_job_status(session, job_id)
    if status_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    if status_row.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "job_not_completed", "current_status": status_row.status},
        )
    payload = await get_output(session, job_id)
    if payload is None:
        # job claims 'completed' but no output row — treat as 409, not 200.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="completed_job_missing_output",
        )
    return payload
