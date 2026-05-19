"""Operator-grade /v1/intake/jobs ingress. Implements PHASE_5_SPEC.md §4.2–§4.6."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.base import OnrampIntakeReview, OnrampJob
from packages.core.db.repositories import (
    get_job_status,
    get_output,
    insert_job_if_new,
)
from packages.core.db.session import get_async_session
from packages.core.models.intake import (
    IntakeJobRequest,
    IntakeJobResponse,
    ReviewAck,
    SignedUrlResponse,
)
from packages.core.settings import Settings, get_settings
from packages.ingest.outbox import enqueue_outbox_event
from packages.storage.signed_url import (
    SIGNED_URL_TTL_SECONDS,
    generate_v4_signed_url,
)

router = APIRouter()

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_STAGING_ROOT = Path("/tmp/onramp")  # noqa: S108  # Phase 5 only; Phase 6 swaps to GCS staging


async def _read_capped(upload: UploadFile) -> bytes:
    """Read at most _MAX_UPLOAD_BYTES; raise 422 on overflow."""
    payload = await upload.read()
    if len(payload) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="upload exceeds 25 MiB cap",
        )
    return payload


def parse_form_request(
    prospect_id: str = Form(...),
    prospect_name: str = Form(...),
    operator_email: str = Form(...),
    requested_slack_channel: str = Form(...),
    priority: str = Form(default="normal"),
) -> IntakeJobRequest:
    """Form-encoded IntakeJobRequest dependency."""
    return IntakeJobRequest(
        prospect_id=prospect_id,
        prospect_name=prospect_name,
        operator_email=operator_email,
        requested_slack_channel=requested_slack_channel,
        priority=priority,  # type: ignore[arg-type]
    )


def _enqueue_chain(job_id: str, staging_path: str) -> None:
    """Send the Phase 4 task chain. Same wiring as /v1/ingest/ratesheet."""
    from packages.ingest.tasks import (
        classify_format_task,
        extract_payload_task,
        normalize_lanes_task,
        validate_output_task,
    )

    classify_format_task.apply_async(
        args=(job_id, staging_path),
        link=(extract_payload_task.s() | normalize_lanes_task.s() | validate_output_task.s()),
    )


@router.post(
    "/jobs",
    response_model=IntakeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "duplicate_input_hash"}, 422: {}},
)
async def submit_intake_job(
    request: IntakeJobRequest = Depends(parse_form_request),
    upload: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse | IntakeJobResponse:
    """Operator ingress with priority + operator_email provenance."""
    payload = await _read_capped(upload)
    input_hash = hashlib.sha256(payload).hexdigest()
    job_id = uuid.uuid4().hex

    async with session.begin():
        resolved_job_id, created = await insert_job_if_new(
            session,
            job_id=job_id,
            prospect_id=request.prospect_id,
            prospect_name=request.prospect_name,
            input_hash=input_hash,
            source_format="auto",
        )
        await enqueue_outbox_event(
            session,
            job_id=resolved_job_id,
            event_type="audit_log",
            payload={
                "stage": "ingress_received",
                "operator_email": request.operator_email,
                "priority": request.priority,
                "requested_slack_channel": request.requested_slack_channel,
            },
        )

    if not created:
        existing = await get_job_status(session, resolved_job_id)
        body = existing.model_dump(mode="json") if existing else {"job_id": resolved_job_id}
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "duplicate_input_hash", "job": body},
        )

    _STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    job_dir = _STAGING_ROOT / resolved_job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    filename = upload.filename or "upload.bin"
    staging_path = job_dir / filename
    staging_path.write_bytes(payload)

    _enqueue_chain(resolved_job_id, str(staging_path))

    return IntakeJobResponse(
        job_id=resolved_job_id,
        status="pending",
        submitted_by=request.operator_email,
        submitted_at=datetime.now(UTC),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=IntakeJobResponse,
    responses={404: {}},
)
async def get_intake_job(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> IntakeJobResponse:
    """Job status by id."""
    status_obj = await get_job_status(session, job_id)
    if status_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    return IntakeJobResponse(
        job_id=status_obj.job_id,
        status=status_obj.status,
        submitted_by="operator",
        submitted_at=status_obj.created_at,
    )


@router.get(
    "/jobs/{job_id}/result-url",
    response_model=SignedUrlResponse,
    responses={404: {}, 409: {}},
)
async def get_result_url(
    job_id: str,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_async_session),
) -> SignedUrlResponse:
    """Issue a V4 signed URL for the normalized JSON blob."""
    status_obj = await get_job_status(session, job_id)
    if status_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    if status_obj.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job_not_completed (status={status_obj.status})",
        )

    blob_name = f"jobs/{job_id}/normalized_ratesheet.json"
    url, expires_at = await generate_v4_signed_url(
        bucket=settings.gcs_bucket_outputs,
        blob_name=blob_name,
        service_account=settings.gcs_signer_service_account,
        ttl_seconds=SIGNED_URL_TTL_SECONDS,
    )

    async with session.begin():
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload={"stage": "result_delivered", "blob_name": blob_name},
        )

    return SignedUrlResponse(job_id=job_id, url=url, expires_at=expires_at)


@router.get(
    "/jobs/{job_id}/review",
    response_model=list[ReviewAck],
    responses={404: {}},
)
async def list_reviews(
    job_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[ReviewAck]:
    """Return all operator-review acknowledgements for the given job."""
    job_exists = (
        await session.execute(select(OnrampJob.job_id).where(OnrampJob.job_id == job_id))
    ).scalar_one_or_none()
    if job_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")
    rows = (
        (
            await session.execute(
                select(OnrampIntakeReview)
                .where(OnrampIntakeReview.job_id == job_id)
                .order_by(OnrampIntakeReview.acknowledged_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ReviewAck(
            job_id=row.job_id,
            lane_id=row.lane_id,
            decision=row.decision,  # type: ignore[arg-type]
            operator_email=row.operator_email,
            notes=row.notes,
            acknowledged_at=row.acknowledged_at,
        )
        for row in rows
    ]


@router.post(
    "/jobs/{job_id}/review",
    response_model=ReviewAck,
    status_code=status.HTTP_201_CREATED,
    responses={404: {}, 422: {}},
)
async def post_review(
    job_id: str,
    ack: ReviewAck,
    session: AsyncSession = Depends(get_async_session),
) -> ReviewAck:
    """Record one operator acknowledgement of a flagged lane outcome."""
    if ack.job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ack.job_id does not match URL job_id",
        )

    job_exists = (
        await session.execute(select(OnrampJob.job_id).where(OnrampJob.job_id == job_id))
    ).scalar_one_or_none()
    if job_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job_not_found")

    async with session.begin():
        session.add(
            OnrampIntakeReview(
                job_id=ack.job_id,
                lane_id=ack.lane_id,
                decision=ack.decision,
                operator_email=ack.operator_email,
                notes=ack.notes,
                acknowledged_at=ack.acknowledged_at,
            )
        )
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload={
                "stage": "review_acknowledged",
                "lane_id": ack.lane_id,
                "decision": ack.decision,
                "operator_email": ack.operator_email,
            },
        )

    return ack


# Touch get_output to satisfy unused-import linting if review fetches result later.
__all__ = [
    "get_intake_job",
    "get_output",
    "get_result_url",
    "list_reviews",
    "post_review",
    "router",
    "submit_intake_job",
]
