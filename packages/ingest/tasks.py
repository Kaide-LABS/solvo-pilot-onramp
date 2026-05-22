"""Celery tasks for Stages 1-4. Implements PHASE_2_SPEC.md §6.3 +
PHASE_3_SPEC.md §6 + PHASE_4_SPEC.md §6.6 + PHASE_6_5_SPEC.md §6.1, §6.3 +
PHASE_6_6_SPEC.md §6.3.

Task names match Solvo_Master_PRD.md §3.4 verbatim:
- tasks.ingest.classify_format
- tasks.ingest.extract_payload
- tasks.ingest.normalize_lanes
- tasks.ingest.validate_output

Phase 6.5 (§6.1) restructures each async task body so that the SQLAlchemy
AsyncEngine is constructed inside the `asyncio.run` loop and disposed in a
`finally` block. This fixes the cross-loop bug where the prior lru-cached
engine retained asyncpg connections bound to a previously-closed loop.

Phase 6.5 (§6.3) adds a `slack_post` outbox row enqueue inside `_validate`'s
terminal transaction, alongside the existing `audit_log` enqueue.

Phase 6.6 (§6.3) fixes Defect 6: each failure-path writes its failure-status
update + audit_log row in its OWN fresh `session.begin()` transaction, then
re-raises. The prior shape (within `_normalize`) wrote the failure status
inside the success-path `session.begin()` block before raising, which caused
SQLAlchemy to roll back the failure write along with the (already-failed)
success-path work — leaving the job row wedged at the intermediate status.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from apps.worker.celery_app import celery_app
from packages.core.db.repositories import (
    insert_output,
    update_job_status,
)
from packages.core.db.session import make_async_engine
from packages.core.settings import get_settings
from packages.ingest.classifier import classify_format
from packages.ingest.excel_extractor import (
    ExcelTooLargeError,
    ExtractionError,
    extract_excel_payload,
)
from packages.ingest.outbox import enqueue_outbox_event

_log = logging.getLogger(__name__)

# Phase 6.6 (§6.3): redact staging paths from failure messages so audit_log
# rows stay PII-clean per §3.10.4. Job-id-keyed paths under /tmp/onramp/
# could leak operator filenames if surfaced verbatim.
_TMP_PATH_RE = re.compile(r"/tmp/onramp/[^\s'\"]+")  # noqa: S108 — path literal is a redaction pattern, not a tempfile path


def _failure_payload(stage: str, exc: BaseException) -> dict[str, Any]:
    """Construct a PII-clean audit_log payload for a task failure.

    `stage` is one of `extract_failed`, `normalize_failed`, `validate_failed`.
    The exception message is truncated to 500 chars after redacting any
    embedded `/tmp/onramp/...` staging paths to the literal `<staging>`.
    See PHASE_6_6_SPEC.md §6.3.
    """
    redacted = _TMP_PATH_RE.sub("<staging>", str(exc))
    return {
        "stage": stage,
        "error_type": type(exc).__name__,
        "error_message": redacted[:500],
    }


async def _commit_failure(
    factory: Any, job_id: str, stage: str, exc: BaseException
) -> None:
    """Write the terminal `failed` status + audit_log row in a fresh transaction.

    Phase 6.6 (§6.3): the failure-status write MUST commit in its own
    `session.begin()` block — separate from any success-path transaction —
    so that the subsequent `raise` cannot trigger a rollback of the
    failure-status update. The Celery task is still marked failed at the
    Celery level after the re-raise; this gives the API a durable signal.
    """
    async with factory() as session, session.begin():
        await update_job_status(session, job_id, new_status="failed", completed=True)
        await enqueue_outbox_event(
            session,
            job_id=job_id,
            event_type="audit_log",
            payload=_failure_payload(stage, exc),
        )


async def _recover_requested_slack_channel(factory: Any, job_id: str) -> str | None:
    """Read requested_slack_channel from the ingress_received audit_log row.

    Phase 6.5 workaround: Phase 5 captured the channel in the audit_log
    outbox payload at intake time rather than on `OnrampJob`. Rather than
    add a column + migration, the validate task recovers the channel from
    that outbox row. This is read-only and idempotent.
    """
    from sqlalchemy import select

    from packages.core.db.base import OnrampOutbox

    async with factory() as session:
        result = await session.execute(
            select(OnrampOutbox.payload)
            .where(OnrampOutbox.job_id == job_id)
            .where(OnrampOutbox.event_type == "audit_log")
        )
        for (payload,) in result.all():
            if isinstance(payload, dict) and payload.get("stage") == "ingress_received":
                channel = payload.get("requested_slack_channel")
                if isinstance(channel, str) and channel:
                    return channel
    return None


async def _classify(job_id: str, staging_path: str) -> str:
    """Run the deterministic classifier and persist the status transition.

    Phase 6.5: owns its own engine for this task's event loop.
    """
    path = Path(staging_path)
    payload = path.read_bytes()
    classified = classify_format(payload, path.name, "auto")

    engine: AsyncEngine = make_async_engine()
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        # Phase 4: EDIFACT joins Excel as a supported terminal format.
        if classified.detected_format not in {"excel", "edifact"}:
            async with factory() as session, session.begin():
                await update_job_status(session, job_id, new_status="failed", completed=True)
            raise ExtractionError(
                f"format {classified.detected_format!r} not supported in Phase 4 "
                f"({classified.reason})"
            )

        async with factory() as session, session.begin():
            await update_job_status(session, job_id, new_status="extracting")
        return classified.detected_format
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.ingest.classify_format", bind=True, max_retries=0)
def classify_format_task(self, job_id: str, staging_path: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 1 task. Returns (job_id, staging_path, fmt) for the linked extract task."""
    fmt = asyncio.run(_classify(job_id, staging_path))
    return {"job_id": job_id, "staging_path": staging_path, "fmt": fmt}


async def _extract(job_id: str, staging_path: str, fmt: str) -> None:
    """Run Stage 2 extraction and commit the output + outbox row atomically.

    Phase 4 widens the supported set: excel | edifact. Other formats are
    rejected at the classifier (Phase 4 _classify) — this branch is
    defense-in-depth. Phase 6.5: per-task engine.
    """
    if fmt not in {"excel", "edifact"}:
        raise ExtractionError(f"Phase 4 extractor handles 'excel' or 'edifact'; got {fmt!r}")

    settings = get_settings()
    engine: AsyncEngine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)

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
            # Phase 6.6 (§6.3): failure-status write + audit_log row in their
            # own fresh transaction, then propagate. The existing _extract
            # failure-handler already exited `session.begin()` before raising
            # (so the failure-status commit was safe), but the audit_log row
            # is new — Phase 6.6 §8 criterion #3 requires it across all three
            # failure paths.
            await _commit_failure(factory, job_id, "extract_failed", exc)
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
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.ingest.extract_payload", bind=True, max_retries=0)
def extract_payload_task(self, upstream: dict[str, str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 2 task. Returns a dict the Phase 3 chain link consumes."""
    asyncio.run(_extract(upstream["job_id"], upstream["staging_path"], upstream["fmt"]))
    return {"job_id": upstream["job_id"]}


# ---------------------------------------------------------------------------
# Phase 3 — Stage 3 N=3 Pro ensemble normalization task.
# ---------------------------------------------------------------------------


async def _normalize(job_id: str) -> None:
    """Read the persisted extraction, run Stage 3, and overwrite atomically.

    Phase 6.5: per-task engine.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from packages.core.db.base import OnrampOutput
    from packages.core.db.repositories import get_output
    from packages.ingest.normalizer import EnsembleError, normalize_lanes

    settings = get_settings()
    engine: AsyncEngine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            extraction = await get_output(session, job_id)
        if extraction is None:
            exc = EnsembleError(f"job {job_id!r} has no extraction output to normalize")
            await _commit_failure(factory, job_id, "normalize_failed", exc)
            raise exc

        # Phase 6.6 (§6.3): heavy LLM work happens OUTSIDE the success-path
        # transaction so that a transient EnsembleError can write its
        # failure-status row in a separate session.begin() without being
        # rolled back. The successful normalize result is then committed in
        # the success-path transaction below.
        try:
            async with factory() as session:
                updated, consensus_results = await normalize_lanes(
                    job_id=job_id,
                    extraction=extraction,
                    session=session,
                    settings=settings,
                )
        except EnsembleError as exc:
            await _commit_failure(factory, job_id, "normalize_failed", exc)
            _log.warning("normalize_lanes: job=%s failed: %s", job_id, exc)
            raise

        async with factory() as session, session.begin():
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
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.ingest.normalize_lanes", bind=True, max_retries=0)
def normalize_lanes_task(self, upstream: dict[str, str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Stage 3 task — runs the N=3 Pro ensemble + consensus + port resolution."""
    asyncio.run(_normalize(upstream["job_id"]))
    return {"job_id": upstream["job_id"]}


# ---------------------------------------------------------------------------
# Phase 4 — Stage 4 deterministic validation + conformal + optional clarify.
# Phase 6.5 (§6.3) — slack_post outbox enqueue alongside audit_log.
# ---------------------------------------------------------------------------


async def _validate(job_id: str) -> None:
    """Stage 4 task body. Implements PHASE_4_SPEC.md §6.6 + PHASE_6_5_SPEC §6.3.

    Reads the normalized payload (Phase 3 output), applies hard rules,
    computes conformal scores from any retained EnsembleVote rows, drafts
    clarification text for flagged lanes, and writes the final payload + the
    terminal completed-status + audit_log row + slack_post row in one
    transaction.

    Phase 6.5: per-task engine; also enqueues `slack_post` outbox row so the
    dispatcher can post the Block Kit summary to the requested Slack channel.
    """
    from pathlib import Path

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from packages.core.db.base import OnrampConformalScore, OnrampOutput
    from packages.core.db.repositories import (
        get_job,
        get_output,
        load_consensus,
        load_votes_by_lane,
    )
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
    from packages.ingest.rules_engine import apply_hard_rules
    from packages.slack.block_kit import build_summary_blocks
    from packages.storage.signed_url import generate_v4_signed_url

    settings = get_settings()
    engine: AsyncEngine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)

        # Phase 6.6 (§6.3): wrap the _validate body so any failure (missing
        # rows, slack-channel recovery, conformal/correction/clarification
        # exceptions) writes a durable failure-status row + audit_log entry
        # before re-raising. Without this the job wedged at status='validating'.
        try:
            async with factory() as session:
                normalized = await get_output(session, job_id)
            if normalized is None:
                raise ExtractionError(
                    f"job {job_id!r} has no normalized output to validate"
                )

            # Load the job row up front so we can read prospect_name. The
            # requested_slack_channel is recovered separately from the
            # ingress_received audit_log outbox row written by the intake
            # route (Phase 5 captured the channel in that payload rather
            # than on the job row; see PHASE_6_5_SPEC §6.3 contract note).
            async with factory() as session:
                job_row = await get_job(session, job_id)
            if job_row is None:
                raise ExtractionError(f"job {job_id!r} vanished before validation")
            slack_channel = await _recover_requested_slack_channel(factory, job_id)
            if not slack_channel:
                raise ExtractionError(
                    f"job {job_id!r} has no requested_slack_channel in audit_log; "
                    "intake route did not enqueue ingress_received payload as expected"
                )

            validated, violations = apply_hard_rules(normalized)

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
                        FlaggedLane(
                            lane=lane, reason="low_confidence", confidence=score.confidence
                        )
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

            # Phase 6.5: build the Slack Block Kit summary + signed URL outside
            # the transaction so the I/O (GCS signer) doesn't hold a Postgres
            # transaction open longer than necessary. Both values land inside the
            # `slack_post` outbox payload, which commits in the same transaction
            # as the audit_log row and the OnrampOutput upsert.
            signed_url, expires_at = await generate_v4_signed_url(
                bucket=settings.gcs_bucket_outputs,
                blob_name=f"jobs/{job_id}/normalized_ratesheet.json",
                service_account=settings.gcs_signer_service_account,
            )
            summary_blocks = build_summary_blocks(
                rs=validated,
                signed_url=signed_url,
                expires_at_iso=expires_at.isoformat(),
            )
            slack_payload: dict[str, Any] = {
                "channel": slack_channel,
                "blocks": summary_blocks,
                "text": f"Solvo Onramp result for {job_row.prospect_name}",
            }

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
                await update_job_status(
                    session, job_id, new_status="completed", completed=True
                )
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
                # Phase 6.5 (§6.3): enqueue the Slack thread reply alongside
                # the audit_log row, inside the same transaction.
                # Transactional-outbox invariant preserved — if validation
                # rolls back, no Slack post leaks.
                await enqueue_outbox_event(
                    session,
                    job_id=job_id,
                    event_type="slack_post",
                    payload=slack_payload,
                )
        except Exception as exc:
            # Phase 6.6 (§6.3): _validate failure-handler. Catches any
            # exception from the body above — missing rows, slack-channel
            # recovery, conformal scoring, conditional correction,
            # clarification drafting, OR the terminal upsert transaction.
            # The failure-status row + audit_log entry commit in their own
            # fresh transaction so the API has a durable `failed` signal.
            # No slack_post outbox row is enqueued on failure path.
            await _commit_failure(factory, job_id, "validate_failed", exc)
            _log.warning("validate_output: job=%s failed: %s", job_id, exc)
            raise
    finally:
        await engine.dispose()


@celery_app.task(name="tasks.ingest.validate_output", bind=True, max_retries=0)
def validate_output_task(self, upstream: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    """Stage 4 task — deterministic rules engine + conformal + audit_log + slack_post."""
    asyncio.run(_validate(upstream["job_id"]))
