"""Celery tasks for Stage 1 + Stage 2. Implements PHASE_2_SPEC.md §6.3.

Task names match Solvo_Master_PRD.md §3.4 verbatim:
- tasks.ingest.classify_format
- tasks.ingest.extract_payload

Phase 2 wiring: classify_format_task.apply_async(link=extract_payload_task.s()).
Celery chord wiring (with normalize_lanes) is Phase 3.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.worker.celery_app import celery_app
from packages.core.db.repositories import (
    insert_output,
    update_job_status,
)
from packages.core.db.session import get_async_engine
from packages.core.settings import get_settings
from packages.ingest.classifier import classify_format
from packages.ingest.excel_extractor import (
    ExcelTooLargeError,
    ExtractionError,
    extract_excel_payload,
)
from packages.ingest.outbox import enqueue_outbox_event

_log = logging.getLogger(__name__)


async def _classify(job_id: str, staging_path: str) -> str:
    """Run the deterministic classifier and persist the status transition."""
    path = Path(staging_path)
    payload = path.read_bytes()
    classified = classify_format(payload, path.name, "auto")

    factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)
    if classified.detected_format != "excel":
        async with factory() as session, session.begin():
            await update_job_status(session, job_id, new_status="failed", completed=True)
        raise ExtractionError(
            f"format {classified.detected_format!r} not supported in Phase 2 ({classified.reason})"
        )

    async with factory() as session, session.begin():
        await update_job_status(session, job_id, new_status="extracting")
    return classified.detected_format


@celery_app.task(name="tasks.ingest.classify_format", bind=True, max_retries=0)
def classify_format_task(self, job_id: str, staging_path: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 1 task. Returns (job_id, staging_path, fmt) for the linked extract task."""
    fmt = asyncio.run(_classify(job_id, staging_path))
    return {"job_id": job_id, "staging_path": staging_path, "fmt": fmt}


async def _extract(job_id: str, staging_path: str, fmt: str) -> None:
    """Run Stage 2 extraction and commit the output + outbox row atomically."""
    if fmt != "excel":
        # Defense-in-depth: classify_format should have already failed the job.
        raise ExtractionError(f"Phase 2 extractor only handles 'excel'; got {fmt!r}")

    settings = get_settings()
    factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)

    # Look up prospect_id from the job row so we can authoritatively stamp the payload.
    async with factory() as session:
        from packages.core.db.repositories import get_job

        job = await get_job(session, job_id)
        if job is None:
            raise ExtractionError(f"job {job_id!r} vanished before extraction")
        prospect_id = job.prospect_id

    try:
        payload, _meta = await extract_excel_payload(
            Path(staging_path), job_id, prospect_id, settings
        )
    except (ExcelTooLargeError, ExtractionError) as exc:
        async with factory() as session, session.begin():
            await update_job_status(session, job_id, new_status="failed", completed=True)
        _log.warning("extract_payload: job=%s failed: %s", job_id, exc)
        raise

    async with factory() as session, session.begin():
        await insert_output(session, job_id=job_id, payload=payload)
        # Phase 3 change: extract transitions to "normalizing", not "completed".
        # normalize_lanes_task owns the final completion + outbox audit_log.
        await update_job_status(session, job_id, new_status="normalizing")
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload={"stage": "extracted", "lane_count": len(payload.lanes)},
        )


@celery_app.task(name="tasks.ingest.extract_payload", bind=True, max_retries=0)
def extract_payload_task(self, upstream: dict[str, str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 2 task. Returns a dict the Phase 3 chain link consumes."""
    asyncio.run(_extract(upstream["job_id"], upstream["staging_path"], upstream["fmt"]))
    return {"job_id": upstream["job_id"]}


# ---------------------------------------------------------------------------
# Phase 3 — Stage 3 N=3 Pro ensemble normalization task.
# ---------------------------------------------------------------------------


async def _normalize(job_id: str) -> None:
    """Read the persisted extraction, run Stage 3, and overwrite atomically."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from packages.core.db.base import OnrampOutput
    from packages.core.db.repositories import get_output
    from packages.ingest.normalizer import EnsembleError, normalize_lanes

    settings = get_settings()
    factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)

    async with factory() as session:
        extraction = await get_output(session, job_id)
    if extraction is None:
        raise EnsembleError(f"job {job_id!r} has no extraction output to normalize")

    async with factory() as session, session.begin():
        try:
            updated, consensus_results = await normalize_lanes(
                job_id=job_id,
                extraction=extraction,
                session=session,
                settings=settings,
            )
        except EnsembleError as exc:
            await update_job_status(session, job_id, new_status="failed", completed=True)
            _log.warning("normalize_lanes: job=%s failed: %s", job_id, exc)
            raise

        # Overwrite the persisted normalized_payload via an upsert.
        await session.execute(
            pg_insert(OnrampOutput)
            .values(
                job_id=job_id,
                normalized_payload=updated.model_dump(mode="json"),
                lane_count=len(updated.lanes),
                flagged_count=len(updated.flagged_for_review),
                rejected_count=len(updated.deterministically_rejected),
            )
            .on_conflict_do_update(
                index_elements=[OnrampOutput.job_id],
                set_={
                    "normalized_payload": updated.model_dump(mode="json"),
                    "lane_count": len(updated.lanes),
                    "flagged_count": len(updated.flagged_for_review),
                    "rejected_count": len(updated.deterministically_rejected),
                },
            )
        )
        await update_job_status(session, job_id, new_status="completed", completed=True)
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload={
                "stage": "normalized",
                "consensus_clean": sum(1 for c in consensus_results if not c.requires_review),
                "flagged": len(updated.flagged_for_review),
            },
        )


@celery_app.task(name="tasks.ingest.normalize_lanes", bind=True, max_retries=0)
def normalize_lanes_task(self, upstream: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    """Stage 3 task — runs the N=3 Pro ensemble + consensus + port resolution."""
    asyncio.run(_normalize(upstream["job_id"]))
