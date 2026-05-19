"""POST /v1/ingest/ratesheet. Implements PHASE_2_SPEC.md §4.1.

Streams the multipart upload to a temp staging dir, hashes it, inserts the
job row, and enqueues the Stage 1 classifier task. Idempotency is enforced
by the unique input_hash constraint — duplicate posts return 409 with the
existing job_id.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.repositories import get_job_status, insert_job_if_new
from packages.core.db.session import get_async_session
from packages.core.models.ingress import RatesheetIngressRequest
from packages.core.models.ratesheet import JobStatus, SourceFormatHint

router = APIRouter()

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
_STAGING_ROOT = Path("/tmp/onramp")  # noqa: S108 — Phase 2 local-only; Phase 5 swaps to GCS


async def parse_form_request(
    prospect_id: str = Form(...),
    prospect_name: str = Form(...),
    source_format_hint: SourceFormatHint = Form("auto"),
    requesting_user_slack_id: str = Form(...),
    callback_channel: str = Form(...),
) -> RatesheetIngressRequest:
    """Validate the form portion of the multipart request via the strict-forbid model."""
    try:
        return RatesheetIngressRequest(
            prospect_id=prospect_id,
            prospect_name=prospect_name,
            source_format_hint=source_format_hint,
            requesting_user_slack_id=requesting_user_slack_id,
            callback_channel=callback_channel,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


async def _read_capped(upload: UploadFile) -> bytes:
    """Read at most _MAX_UPLOAD_BYTES + 1 from the upload, raising 422 on overflow."""
    data = await upload.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="upload_exceeds_25_MiB_cap",
        )
    return data


def _enqueue_classify(job_id: str, staging_path: str) -> None:
    """Send the Celery task. Imported lazily so unit tests can patch this symbol.

    Phase 3 wiring (PHASE_3_SPEC §6.4): the chain extends through
    normalize_lanes_task. classify → extract → normalize.
    """
    from packages.ingest.tasks import (
        classify_format_task,
        extract_payload_task,
        normalize_lanes_task,
    )

    classify_format_task.apply_async(
        args=(job_id, staging_path),
        link=extract_payload_task.s() | normalize_lanes_task.s(),
    )


@router.post(
    "",
    response_model=JobStatus,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        409: {"description": "duplicate_input_hash"},
        422: {"description": "validation_error"},
    },
)
async def submit_ratesheet(
    request: RatesheetIngressRequest = Depends(parse_form_request),
    upload: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse | JobStatus:
    """Accept a ratesheet upload, persist the job, and enqueue Stage 1."""
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
            source_format=request.source_format_hint,
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

    _enqueue_classify(resolved_job_id, str(staging_path))

    status_obj = await get_job_status(session, resolved_job_id)
    assert status_obj is not None  # row was just inserted in the same session
    return status_obj
