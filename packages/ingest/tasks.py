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
    # Phase 4: EDIFACT joins Excel as a supported terminal format.
    if classified.detected_format not in {"excel", "edifact"}:
        async with factory() as session, session.begin():
            await update_job_status(session, job_id, new_status="failed", completed=True)
        raise ExtractionError(
            f"format {classified.detected_format!r} not supported in Phase 4 ({classified.reason})"
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
    """Run Stage 2 extraction and commit the output + outbox row atomically.

    Phase 4 widens the supported set: excel | edifact. Other formats are
    rejected at the classifier (Phase 4 _classify) — this branch is
    defense-in-depth.
    """
    if fmt not in {"excel", "edifact"}:
        raise ExtractionError(f"Phase 4 extractor handles 'excel' or 'edifact'; got {fmt!r}")

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
        if fmt == "edifact":
            from packages.ingest.edifact_extractor import (
                EdifactExtractionError,
                extract_edifact_payload,
            )

            try:
                payload, _meta = await extract_edifact_payload(
                    Path(staging_path), job_id, prospect_id, settings
                )
            except EdifactExtractionError as exc:
                raise ExtractionError(str(exc)) from exc
        else:
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
        # Phase 5 carry-forward: persist per-lane EnsembleVote snapshots so
        # validate_output_task can compute calibrated conformal scores.
        from packages.ingest.normalizer import _persist_consensus_votes

        await _persist_consensus_votes(session, job_id, consensus_results)

        # Phase 4: normalize transitions to "validating", not "completed".
        # validate_output_task owns the final transition + audit_log.
        await update_job_status(session, job_id, new_status="validating")
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
def normalize_lanes_task(self, upstream: dict[str, str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 3 task — runs the N=3 Pro ensemble + consensus + port resolution."""
    asyncio.run(_normalize(upstream["job_id"]))
    return {"job_id": upstream["job_id"]}


# ---------------------------------------------------------------------------
# Phase 4 — Stage 4 deterministic validation + conformal + optional clarify.
# ---------------------------------------------------------------------------


async def _validate(job_id: str) -> None:
    """Stage 4 task body. Implements PHASE_4_SPEC.md §6.6.

    Reads the normalized payload (Phase 3 output), applies hard rules,
    computes conformal scores from any retained EnsembleVote rows, drafts
    clarification text for flagged lanes, and writes the final payload + the
    terminal completed-status + audit_log row in one transaction.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from packages.core.db.base import OnrampOutput
    from packages.core.db.repositories import get_output
    from packages.ingest.rules_engine import apply_hard_rules

    factory = async_sessionmaker(get_async_engine(), expire_on_commit=False)

    async with factory() as session:
        normalized = await get_output(session, job_id)
    if normalized is None:
        raise ExtractionError(f"job {job_id!r} has no normalized output to validate")

    validated, violations = apply_hard_rules(normalized)

    # Phase 5 carry-forward (PHASE_5_SPEC §6.5 + §7.1):
    # conformal scoring → conditional correction → clarification.
    from pathlib import Path

    from packages.core.db.base import OnrampConformalScore
    from packages.core.db.repositories import load_consensus, load_votes_by_lane
    from packages.core.models.conformal import ConformalScore
    from packages.core.models.normalization import ConsensusResult, EnsembleVote
    from packages.core.models.ratesheet import FlaggedLane
    from packages.ingest.clarification import draft_clarification
    from packages.ingest.conformal import (
        accepts,
        compute_conformal_score,
        load_calibration,
    )
    from packages.ingest.correction import conditional_correction

    settings = get_settings()
    calibration = load_calibration(Path("fixtures/conformal_calibration_v1.json"))

    async with factory() as session:
        votes_payload_by_lane = await load_votes_by_lane(session, job_id)

    # Build EnsembleVote objects per lane for conformal scoring.
    votes_by_lane: dict[str, list[EnsembleVote]] = {}
    for lane_id, raw_votes in votes_payload_by_lane.items():
        votes_by_lane[lane_id] = [EnsembleVote.model_validate(v) for v in raw_votes]

    conformal_by_lane: dict[str, ConformalScore] = {}
    low_confidence: list[FlaggedLane] = []
    for lane in validated.lanes:
        votes = votes_by_lane.get(lane.lane_id, [])
        if not votes:
            continue
        score = compute_conformal_score(lane.lane_id, votes, calibration)
        conformal_by_lane[lane.lane_id] = score
        if not accepts(score):
            low_confidence.append(
                FlaggedLane(lane=lane, reason="low_confidence", confidence=score.confidence)
            )

    # Conditional correction for no-majority flagged lanes.
    correction_triggers = 0
    surviving_flags: list[FlaggedLane] = []
    for flagged in validated.flagged_for_review:
        if flagged.reason != "no_majority":
            surviving_flags.append(flagged)
            continue
        async with factory() as session:
            prior_payload = await load_consensus(session, job_id, flagged.lane.lane_id)
        if prior_payload is None:
            surviving_flags.append(flagged)
            continue
        try:
            prior = ConsensusResult.model_validate(prior_payload)
        except Exception:
            surviving_flags.append(flagged)
            continue
        corrected = await conditional_correction(prior, settings)
        correction_triggers += 1
        if corrected.consensus_lane is None:
            surviving_flags.append(flagged)

    # Drop low-confidence flags only after correction so we don't double-count.
    surviving_flags.extend(low_confidence)

    # Clarification text (numeric-free) per surviving flag.
    clarifications: dict[str, str] = {}
    for f in surviving_flags:
        clarifications[f.lane.lane_id] = await draft_clarification(f, settings)

    validated = validated.model_copy(update={"flagged_for_review": surviving_flags})

    async with factory() as session, session.begin():
        await session.execute(
            pg_insert(OnrampOutput)
            .values(
                job_id=job_id,
                normalized_payload=validated.model_dump(mode="json"),
                lane_count=len(validated.lanes),
                flagged_count=len(validated.flagged_for_review),
                rejected_count=len(validated.deterministically_rejected),
            )
            .on_conflict_do_update(
                index_elements=[OnrampOutput.job_id],
                set_={
                    "normalized_payload": validated.model_dump(mode="json"),
                    "lane_count": len(validated.lanes),
                    "flagged_count": len(validated.flagged_for_review),
                    "rejected_count": len(validated.deterministically_rejected),
                },
            )
        )
        # Update per-lane conformal scores with calibrated confidence values.
        for lane_id, score in conformal_by_lane.items():
            await session.execute(
                pg_insert(OnrampConformalScore)
                .values(
                    job_id=job_id,
                    lane_id=lane_id,
                    confidence=score.confidence,
                    ensemble_votes={"calibration_id": score.calibration_id},
                )
                .on_conflict_do_update(
                    index_elements=[
                        OnrampConformalScore.job_id,
                        OnrampConformalScore.lane_id,
                    ],
                    set_={
                        "confidence": score.confidence,
                        "ensemble_votes": {"calibration_id": score.calibration_id},
                    },
                )
            )
        await update_job_status(session, job_id, new_status="completed", completed=True)
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload={
                "stage": "validated",
                "violations": [v.rule_id for v in violations],
                "lane_count": len(validated.lanes),
                "rejected_count": len(validated.deterministically_rejected),
                "conformal_summary": {
                    "scored": len(conformal_by_lane),
                    "low_confidence": len(low_confidence),
                },
                "correction_triggered": correction_triggers,
                "clarifications": len(clarifications),
            },
        )


@celery_app.task(name="tasks.ingest.validate_output", bind=True, max_retries=0)
def validate_output_task(self, upstream: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    """Stage 4 task — deterministic rules engine + conformal + audit_log."""
    asyncio.run(_validate(upstream["job_id"]))
