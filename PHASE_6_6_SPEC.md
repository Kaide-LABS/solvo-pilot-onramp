# PHASE 6.6 SPEC — Second Closure Patch

**Output of Step 2 (Phase 6.6 spec generation).** Consumes the Stage F.3 re-run halt at commit `c24710b`, `HUMAN_INTERVENTION_REQUEST_V2.md` (the four defects 4-7), `SMOKE_TEST_LOG.md` §"Stage F.3 re-run HALTED," `BUILD_COMPLETE_V2.md` (the Phase 6.5 closure record), and the live state of the codebase as committed at `c24710b`. Feeds: a single Step 3A build cycle, a single Step 3B review cycle, then Sprint 2 closure is final.

---

## §0 — Phase Plan Header

**This is Phase 6.6 of the Sprint 1 build — a second closure patch following the Step 4 Stage F.3 re-run halt at commit `c24710b`.** Phase 6.5 fixed the three named defects from the original Stage F.3 halt (Celery / async-SQLAlchemy cross-loop, missing demo fixtures, missing `slack_post` outbox enqueue). The post-Phase-6.5 F.3 re-run surfaced **four additional defects** (4, 5, 6, 7) plus one structural budget mismatch. Phase 6.6 commits the two in-flight patches Claude Code applied during the re-run (Defects 4 + 5) and adds the two outstanding fixes (Defects 6 + 7). After Phase 6.6 lands (Step 3A build approved by Step 3B review), Sprint 2 closure is genuinely final and demo recording is authorized via a final Stage F.3-F.5 re-run against a 15-lane K+N fixture under a recalibrated 180 s budget.

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor. |
| ✅ Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load. |
| ✅ Phase 4 | 28–36 | EDIFACT, Stage 4 rules engine, audit trail, `/internal/v1/audit`. |
| ✅ Phase 5 | 36–48 | Slack + intake + dispatcher + Phase 4 wiring closure. |
| ✅ Phase 6 | 48–60 | Cloud Run europe-west4 deployment + lifecycle. |
| ✅ Phase 6.5 | post-F.3 halt #1 | Defects 1-3 (Celery engine, fixtures, slack_post). |
| **Phase 6.6** | post-F.3 halt #2 | **Defects 4-7: shared staging volume, Vertex client cache, failure-handler rollback, F.3 budget vs fixture mismatch.** |

The four defects (referenced by name throughout this spec):

- **Defect 4 — Missing shared staging volume in `docker-compose.yml`**: api and worker containers run in separate filesystems. The intake route writes the uploaded payload to the api container's local `/tmp/onramp/<job_id>/…`; the Celery `_extract` task in the worker container cannot read it. Cloud Run hides this gap (staging via GCS); the local smoke stack breaks immediately. Phase 5/6 should have caught it.
- **Defect 5 — `get_vertex_client` module-level cache replicates the Defect-1 cross-loop bug**: `packages/compliance/vertex_client.py` caches the `genai.Client` by `(project, location)`. The Vertex AI boot handshake populates the cache inside the boot-validator `asyncio.run` loop. Celery's prefork pool copies this module state into each `ForkPoolWorker`. The httpx AsyncClient inside the inherited client has connections bound to the parent's (now-closed) loop. The first `_extract` / `_normalize` task call in any forked worker crashes with `RuntimeError: Event loop is closed`.
- **Defect 6 — Failure-handler `update_job_status` writes get rolled back**: in `packages/ingest/tasks.py`, each of `_extract`, `_normalize`, `_validate` writes the `status='failed'` transition inside an `async with session.begin():` block. When the same block then `raise`s, SQLAlchemy's context manager rolls back the transaction — undoing the failure-status write. Jobs that hit transient errors (e.g., Pro-call timeout) wedge at intermediate statuses (`extracting`, `normalizing`, `validating`) permanently. The API has no failure signal to surface.
- **Defect 7 — F.3 acceptance budget vs fixture size mismatch (structural)**: F.3.1's 90 s budget is mathematically incompatible with a 50-lane K+N fixture under the N=3 Pro ensemble. PHASE_6_5_SPEC §6.3's own benchmark is 30–60 s for a 3-lane fixture; 50 lanes is ~17× that. Per-lane ensemble parallelism is already shipped (see §6.4.2 below) — the actual lever is the lane count. Phase 6.6 shrinks K+N to 15 lanes (~150 s) and recalibrates F.3.1 to 180 s.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 6.6.** Per ULTIMATE_PRD §4.7, the provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 6.6 introduces no new academic claims — it is pure bug-fix, fixture-shrink, and PRD-narrative work — so no citation gate runs.

---

## §1 — Files Added or Modified

**Modified:**

- `docker-compose.yml` — **MODIFIED**. Commit Claude Code's in-flight working-tree patch from the F.3 re-run halt: add a named volume `staging` mounted at `/tmp/onramp` on both `api` and `worker` services. (Defect 4.)
- `packages/compliance/vertex_client.py` — **MODIFIED**. Commit Claude Code's in-flight working-tree patch: remove the module-level `_client_cache`; `get_vertex_client(settings)` constructs a fresh `genai.Client` per call. Module-level singleton replaced by per-call construction. (Defect 5.)
- `packages/ingest/tasks.py` — **MODIFIED**. Apply the option-(b) failure-handler refactor across `_extract`, `_normalize`, AND `_validate`. The failure-status `update_job_status(..., new_status="failed", completed=True)` plus its companion `audit_log` row commit in their own fresh `session.begin()` block, distinct from the success-path transaction. The `raise` propagates AFTER the failure write commits. (Defect 6.)
- `data/_generate.py` — **MODIFIED**. Reduce the K+N fixture from 50 lanes to 15 lanes. Reposition the three embedded broken lanes (Lane 7 ZZZZZ, Lane 11 negative rate, Lane 14 expired date). Reduce merged-cell rate-tier header rows from 5 to 3 to fit the smaller body. Determinism (Phase 6.5 review patch — `dcterms:modified` rewrite + sorted zip members + RNG seed) is preserved. (Defect 7 fixture shrink.)
- `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` — **REGENERATED**. New 15-lane content. The other three fixtures (`broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi`) are NOT regenerated and remain byte-identical to their Phase 6.5 versions. (Defect 7.)
- `Solvo_Master_PRD.md` §3.3 — **MODIFIED**. Update the Magic Moment narrative from "50-lane spot rate book" to a 15-lane demonstration. Single-paragraph change. §3.4 and the §5 Path-1 voiceover are NOT touched.
- `PHASE_6_5_SPEC.md` §6.2 — **MODIFIED**. Append a §6.2.1 supersession note (≤5 lines): "Phase 6.6 reduces the K+N fixture from 50 lanes to 15 lanes and recalibrates the F.3.1 budget from 90 s to 180 s. See PHASE_6_6_SPEC.md §6.4." Do NOT rewrite or remove existing Phase 6.5 §6.2 content.
- `tests/integration/test_pipeline_e2e.py` — **MODIFIED**. Two changes:
  - Existing happy-path test now runs against the 15-lane K+N fixture (adjust expected counts from `~45/~2/~3` to `~11/~1-2/~2`).
  - Add a new regression test for Defect 6: drive a job into normalize, inject a `Pro call timeout` (or equivalent transient failure) via test double, assert the job reaches `status='failed'` AND that `onramp_outbox` contains an `audit_log` row with `payload.stage == "normalize_failed"`.

**Added:** none.

**Deleted:** none. `HUMAN_INTERVENTION_REQUEST_V2.md` stays as the historical record of the halt; do NOT remove it.

> **Note on the `_recover_requested_slack_channel` helper introduced in Phase 6.5**: still in `packages/ingest/tasks.py`, still reads from the `ingress_received` audit_log row, still safe (outbox rows are not deleted, only marked `delivered_at`). Phase 6.6 does NOT touch this helper.

---

## §2 — Pip Dependencies

**No new top-level dependencies.** All fixes use the existing dependency set. `pytest-celery` is still not required; the Defect 6 regression test can use the existing fixture pattern (test doubles + the running compose worker, gated by `SOLVO_RUN_E2E_TESTS=1`).

---

## §3 — Pydantic Schemas

**No new schemas.** The failure-path `audit_log` payload uses an existing-shaped dict (free-form `payload: dict[str, Any]` on `OnrampOutbox.payload`). The shape is documented in §6.3.

---

## §4 — FastAPI Route Signatures

**No route changes.** All four defects live in worker / compose / generator / PRD-narrative paths.

---

## §5 — Alembic Migration

**No migration.** Phase 6.6 is runtime / behaviour / topology / fixture fixes only. The terminal migration head stays at `0004_intake_review`.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 4 Fix: Shared Staging Volume

**Problem (precise statement).** The intake route at `apps/api/routes/intake.py` writes the uploaded payload to `_STAGING_ROOT / resolved_job_id / filename`, where `_STAGING_ROOT = Path("/tmp/onramp")`. The `_extract` Celery task in the worker container then opens that same path. The api and worker run as separate containers in `docker-compose.yml`, each with its own filesystem layer. Without a shared volume mount, the worker's `/tmp/onramp/...` is empty and `_extract` dies with `FileNotFoundError`. Cloud Run masks this gap because the production deployment uses GCS as the inter-service handoff store; the local compose smoke stack does not.

**Fix (precise statement).** Add a docker named volume `staging` and mount it at `/tmp/onramp` on both `api` and `worker` services. Dispatcher does not need the mount (it touches Postgres + Redis + Slack only). The patch is exactly the one Claude Code applied in the working tree during the F.3 re-run halt:

```yaml
# docker-compose.yml (excerpt — diff vs the c24710b committed copy)
services:
  api:
    # ...
    volumes:
      - ${USERPROFILE:-${HOME}}/AppData/Roaming/gcloud:/gcp-adc:ro
      - staging:/tmp/onramp          # NEW
    # ports / depends_on / healthcheck unchanged

  worker:
    # ...
    volumes:
      - ${USERPROFILE:-${HOME}}/AppData/Roaming/gcloud:/gcp-adc:ro
      - staging:/tmp/onramp          # NEW
    # depends_on / healthcheck unchanged

volumes:
  pgdata:
  staging:                            # NEW
```

**Behaviour after the fix.** The api writes to a path under `/tmp/onramp` inside the shared volume; the worker reads the same path. The volume is named (not bind-mounted to a host path) so it survives container recreates but can be wiped via `docker compose down -v` when starting from clean state.

**Cloud Run note.** The production deploy stays on GCS for inter-service staging; this volume is a local-compose-only artefact. The infra/terraform module is NOT touched.

### §6.2 — Defect 5 Fix: Vertex Client Per-Call Construction

**Problem (precise statement).** `packages/compliance/vertex_client.py:get_vertex_client(settings)` caches the constructed `genai.Client` in a module-level dict keyed by `(gcp_project_id, vertex_location)`. The Vertex AI handshake during boot validation calls this function from the boot-validator `asyncio.run` loop, populating the cache. That loop then closes when boot validation completes.

Celery's worker uses the `prefork` execution pool. The MainProcess (which runs boot validators) is forked into N ForkPoolWorker processes. POSIX `fork()` copies the parent's memory image, including `_client_cache`. Each forked worker inherits a `genai.Client` whose internal `httpx.AsyncClient` references the parent's now-closed loop via its connection pool.

The first task that calls `get_vertex_client(settings)` in any forked worker gets back the inherited client, issues a `client.aio.models.generate_content(...)` call, and the cleanup path inside httpx's connection-pool error handler trips `loop.call_soon(...)` on the closed parent loop, surfacing as `RuntimeError: Event loop is closed`.

This is **exactly the Defect-1 pattern** Phase 6.5 fixed for the SQLAlchemy engine — different cached client, same underlying hazard.

**Fix (precise statement).** Remove the cache. Construct a fresh client per call. The patch is exactly the one Claude Code applied in the working tree during the F.3 re-run halt:

```python
# packages/compliance/vertex_client.py — full new body of the function

from __future__ import annotations
from typing import TYPE_CHECKING

from packages.core.settings import Settings

if TYPE_CHECKING:
    from google.genai import Client


def get_vertex_client(settings: Settings) -> Client:
    """Construct a fresh Vertex AI client bound to the configured location.

    NOT cached. The genai Client wraps an httpx AsyncClient whose connections
    are bound to the asyncio loop that opens them. Module-level caching
    survives Celery's prefork into ForkPoolWorker children, inheriting a
    connection pool bound to a closed loop and surfacing as
    `RuntimeError: Event loop is closed` on the first task call.

    Per-call construction mirrors the Phase 6.5 `make_async_engine` contract:
    each Celery task owns its own client for the duration of its
    `asyncio.run(...)` invocation. The FastAPI lifespan likewise constructs
    per-handshake (boot validators) and per-request (no request handler
    currently uses Vertex directly).
    """
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_location,
    )
```

**Caller-side audit.** Every existing caller already invokes `get_vertex_client(settings)` once at the top of its async body. No caller assumes the returned client is shared. Confirmed callers (the spec is documenting the contract, not asking the build agent to modify them):

- `packages/ingest/normalizer.py:normalize_lanes` — calls `client = get_vertex_client(settings)` once before iterating lanes; passes `client` to `_ensemble_for_lane`.
- `packages/ingest/excel_extractor.py:extract_excel_payload` — calls once.
- `packages/ingest/edifact_extractor.py:extract_edifact_payload` — calls once.
- `packages/ingest/correction.py:conditional_correction` — calls once per flagged lane.
- `packages/ingest/clarification.py:draft_clarification` — calls once per flagged lane.
- `packages/compliance/boot_validators.py` (vertex_ai_handshake + vertex_ai_compliance_handshake) — calls once each.

The build agent SHOULD verify each caller still receives a `genai.Client` instance with the same shape. No further refactor is required.

**Trade-off (recorded).** Per-call construction adds the gRPC channel-setup latency (~50–100 ms) to every Celery task. Acceptable for demo scale. The worker-process-resident-loop refactor (Option C from the original `HUMAN_INTERVENTION_REQUEST.md`) remains the production-grade path; it is **out of scope** for Phase 6.6 and would deserve its own dedicated phase in any post-engagement sprint.

### §6.3 — Defect 6 Fix: Separate-Transaction Failure Handler

**Problem (precise statement).** Each ingest task body in `packages/ingest/tasks.py` follows the same shape (current, broken):

```python
async def _normalize(job_id: str) -> None:
    engine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        # ... preamble (reads) ...

        async with factory() as session, session.begin():
            try:
                updated, consensus_results = await normalize_lanes(...)
            except EnsembleError as exc:
                await update_job_status(
                    session, job_id, new_status="failed", completed=True
                )
                _log.warning("normalize_lanes: job=%s failed: %s", job_id, exc)
                raise   # <— rolls back the failed-status update above
            # ... success-path upserts + audit_log ...
    finally:
        await engine.dispose()
```

When `EnsembleError` is raised inside the `except` block, the `raise` propagates out of the `session.begin()` context manager. SQLAlchemy's `AsyncSessionTransaction.__aexit__` rolls back the transaction on any exception. The `update_job_status(... "failed")` write is rolled back along with the (already-failed) success-path work. Result: the job row stays at the intermediate status (`normalizing` in the observed case, `extracting` or `validating` in symmetrical cases). The Celery task is marked failed at Celery's level (acks_late + max_retries=0 means it dead-letters), but the operator-facing API has no signal.

**Fix (precise statement).** Move the failure-status write into its own fresh transaction, OUTSIDE the success-path `session.begin()`. Apply the option-(b) pattern across `_extract`, `_normalize`, AND `_validate`. Illustrative for `_normalize`:

```python
async def _normalize(job_id: str) -> None:
    settings = get_settings()
    engine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)

        async with factory() as session:
            extraction = await get_output(session, job_id)
        if extraction is None:
            raise EnsembleError(f"job {job_id!r} has no extraction output to normalize")

        # Heavy work that might raise — do it OUTSIDE the success-path tx
        # so we can surface the failure cleanly.
        try:
            async with factory() as session:
                updated, consensus_results = await normalize_lanes(
                    job_id=job_id,
                    extraction=extraction,
                    session=session,
                    settings=settings,
                )
        except EnsembleError as exc:
            # Phase 6.6: write failure status in its own fresh transaction.
            async with factory() as failure_session, failure_session.begin():
                await update_job_status(
                    failure_session, job_id, new_status="failed", completed=True
                )
                await enqueue_outbox_event(
                    failure_session,
                    job_id=job_id,
                    event_type="audit_log",
                    payload=_failure_payload("normalize_failed", exc),
                )
            _log.warning("normalize_lanes: job=%s failed: %s", job_id, exc)
            raise   # propagate so Celery records the failure

        # Success path: single transaction, unchanged shape.
        async with factory() as session, session.begin():
            # upsert OnrampOutput with normalized_payload,
            # _persist_consensus_votes(session, job_id, consensus_results),
            # update_job_status -> "validating",
            # enqueue_outbox_event "audit_log" stage="normalized".
            ...
    finally:
        await engine.dispose()
```

**Helper (new, module-private).** Introduce a single helper to keep the failure-payload shape consistent and PII-clean:

```python
# packages/ingest/tasks.py — new module-private helper

import re

_TMP_PATH_RE = re.compile(r"/tmp/onramp/[^\s'\"]+")

def _failure_payload(stage: str, exc: BaseException) -> dict[str, Any]:
    """Construct a PII-clean audit_log payload for a task failure.

    - `stage` is one of `extract_failed`, `normalize_failed`, `validate_failed`.
    - `error_type` is the exception class name (str).
    - `error_message` is the exception's str() truncated to 500 chars with
      any embedded `/tmp/onramp/...` staging paths redacted to `<staging>` so
      the audit_log row cannot leak operator filenames or job-id-keyed paths
      beyond what §3.10.4 already permits.
    """
    raw = str(exc)
    redacted = _TMP_PATH_RE.sub("<staging>", raw)
    return {
        "stage": stage,
        "error_type": type(exc).__name__,
        "error_message": redacted[:500],
    }
```

**Per-task application:**

- **`_extract`**: catch the existing `(ExcelTooLargeError, ExtractionError)` block. Write the failure payload with `stage="extract_failed"`. Same pattern.
- **`_normalize`**: catch `EnsembleError`. Write `stage="normalize_failed"`. This is the surfaced defect.
- **`_validate`**: catch the existing `ExtractionError` cases (from the prior-stage row lookup) AND any unexpected exception that arises during conformal scoring / correction / clarification. Write `stage="validate_failed"`. The Slack `slack_post` outbox row is NOT enqueued on failure — only success generates a Slack thread reply.

**Status-machine contract (preserved).** A job row's `status` column follows:

```
pending → extracting → normalizing → validating → completed
                ↓             ↓             ↓
              failed        failed        failed
```

Phase 6.6 makes each `→ failed` transition durably visible to the API.

**Transactional-outbox invariant.** Success-path outbox rows still commit in the same transaction as the `OnrampOutput` upsert and `OnrampJob.status` update. The failure-path outbox row commits in a separate fresh transaction. This is intentional — failure IS the terminal state of the job, not a side-effect to be undone. The §2.4 invariant is preserved in spirit (the failure-row write and the failure-status write are atomic with respect to each other; either both commit or neither does).

**PII contract.** §3.10.4 already requires audit_log payloads to be PII-clean. The new `_failure_payload` helper redacts `/tmp/onramp/...` staging paths from the truncated error string. Exception class names and the 500-char message head are considered safe (no PII; the operator email and Slack channel never appear in exception messages from these code paths).

### §6.4 — Defect 7 Fix: Fixture Shrink + F.3 Budget Recalibration

#### §6.4.1 — K+N Fixture Shrink (50 → 15 lanes)

**Current state.** `data/_generate.py:_generate_kn_fixture` (Phase 6.5) emits a 50-row body with 5 merged-cell rate-tier header rows interleaved. Three deliberate breakages at lane indices 23, 31, 47. Expected normalized/flagged/rejected at `~45 / ~2 / ~3`.

**Phase 6.6 target.** 15 lanes. 3 merged-cell rate-tier header rows. Same column count (~50 columns) and same visual messiness — the demo's "magic moment" comes from the obfuscation density (port-code formats, surcharge columns, prose-format dates) more than the row count. Broken-lane positions move to lane indices that fit the smaller body:

- **Lane 7** — `origin_port = "ZZZZZ"`. Stage 4 deterministic rejection. Rule citation: `port_unknown_unlocode`.
- **Lane 11** — `base_rate_usd = -1500.00`. Stage 4 deterministic rejection. Rule citation: `negative_base_rate`.
- **Lane 14** — `expiry_date = "Feb 1 2025"` (past). Stage 4 flagged for review. Rule citation: `validity_window_in_the_past`.

**Merged-cell rate-tier header positions (3 rows, down from 5).** Rough placement: rows 2 ("STANDARD RATES"), 9 ("SPOT RATES Q2 2026"), 14 ("RF / TEMP-CONTROLLED"). The build agent has discretion on exact row indices as long as they fall between data rows and don't overlap the three broken-lane positions.

**Expected pipeline output for the 15-lane fixture:**

- **11 normalized lanes** ±2 (15 − 2 rejected − 1 flagged − 1-2 expected ensemble disagreements)
- **1–2 flagged for review** ±1 (Lane 14 + possibly 1 ambiguity from an obfuscated port)
- **2 deterministically rejected** ±1 (Lane 7 + Lane 11; possibly +1 from ensemble disagreement escalation)

Tolerance bands are tighter than the 50-lane version because variance scales sub-linearly with lane count.

**Determinism contract (preserved).** The Phase 6.5 review patch (`fix: Phase 6.5 review patches`, commit `518232d`) ensured byte-identical re-runs via:
- Pinned `random.Random(0x5010_06_2026)` RNG seed
- `wb.properties.created` / `wb.properties.modified` pinned to `datetime(2026, 5, 1, 0, 0, 0)`
- Zip-rewrite pass with sorted member ordering and `dcterms:modified` regex replacement in `docProps/core.xml`

All three mechanisms remain in place after the shrink. `python data/_generate.py` must produce byte-identical 15-lane fixtures across re-runs (acceptance criterion §8.6).

**Other fixtures NOT regenerated.** `broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi` are unchanged from their Phase 6.5 versions. Their SHA-256 hashes must match the post-`518232d` values.

#### §6.4.2 — Per-Lane Ensemble Parallelization (Already Shipped — Contract Lock)

**Observation from the F.3 halt log read.** `packages/ingest/normalizer.py:_ensemble_for_lane` is **already** using `asyncio.gather(*coros, return_exceptions=True)` wrapped in `asyncio.wait_for(..., timeout=_TOTAL_BUDGET_SECONDS)`. The N=3 Pro calls fire concurrently per lane. This was shipped in Phase 3 and survived through Phase 6.5.

The 5+ minute wall time observed during the F.3 re-run wasn't sequential ensemble — it was 50 sequential **lanes**, each running its 3-call parallel ensemble at ~6–10 s per lane. That gives 300–500 s, which matches the observed runtime.

**Phase 6.6 contract.** The per-lane ensemble parallelism is preserved verbatim. Lanes themselves remain sequential. The build agent MUST NOT introduce lane-level parallelism (lane-level concurrency would burst N=3 × 15 = 45 concurrent Pro requests, hitting Vertex's burst rate limits and complicating the architectural story Bajaj will probe).

**Documented signature (already in code, restated here as a lock):**

```python
async def _ensemble_for_lane(client: Any, lane: LaneRecord) -> ConsensusResult:
    """Run three Pro calls in parallel and aggregate via majority vote."""
    reference_block = _reference_block_for(lane)
    coros = [
        _one_pro_call(client, lane, cast(Literal[0, 1, 2, 3, 4], i), temp, reference_block)
        for i, temp in enumerate(_TEMPERATURES)
    ]
    votes_or_exc = await asyncio.wait_for(
        asyncio.gather(*coros, return_exceptions=True),
        timeout=_TOTAL_BUDGET_SECONDS,
    )
    votes: list[EnsembleVote] = []
    for v in votes_or_exc:
        if isinstance(v, BaseException):
            raise EnsembleError(f"ensemble call failed: {v}") from v
        votes.append(v)
    if len(votes) != 3:
        raise EnsembleError(f"expected 3 votes, got {len(votes)}")
    return majority_consensus(lane.lane_id, votes)
```

The `_TOTAL_BUDGET_SECONDS = 45.0` and `_PER_CALL_TIMEOUT_SECONDS = 20.0` constants stay as-is. The single-Pro-call timeout from the F.3 halt (a transient `Pro call timeout at T=0.1`) is a real intermittent failure on the global endpoint, not a structural defect; Defect 6's fix ensures any single-lane timeout durably fails the job rather than wedging it.

#### §6.4.3 — F.3 Acceptance Budget Recalibration

PHASE_6_5_SPEC §8 criterion #2 (acceptance criterion #1 in the Step 4 prompt) said "Total runtime under 90 seconds." Phase 6.6 replaces it.

**Expected end-to-end latency for the 15-lane K+N fixture:**

| Stage | Latency | Notes |
|---|---|---|
| Stage 1 classify | ~1 s | Deterministic; no LLM call. |
| Stage 2 extract | ~20–30 s | One Flash call with retries. |
| Stage 3 normalize | ~150 s | 15 lanes × ~10 s parallel-per-lane ensemble. |
| Stage 4 validate | ~5–15 s | Deterministic rules + conditional correction (0–2 Pro calls). |
| Dispatcher pickup | ≤5 s | Beat is every 5 s; slack_post delivered within 5–10 s of validate commit. |

**Total expected end-to-end: ~3 minutes (180 seconds).**

**New F.3 acceptance criteria (Phase 6.6 supersedes Phase 6.5 §8):**

- **F.3.1 (revised):** Total runtime under **180 seconds** per K+N Magic Moment run.
- **F.3.2 (revised):** Output counts within the 15-lane bands:
  - Normalized: 11 ±2 (9–13 acceptable)
  - Flagged: 1–2 ±1 (0–3 acceptable)
  - Rejected: 2 ±1 (1–3 acceptable)
- **F.3.3 (unchanged):** Outbox table contains BOTH `audit_log` (stage=`validated`) AND `slack_post` rows for the job_id. `slack_post.delivered_at` populates within 5–10 s of validation commit.
- **F.3.4 (revised):** Lane-by-lane output ≥95% identical across the 3 runs. (Same metric as Phase 6.5; the smaller lane count makes the metric tighter and easier to inspect.)
- **F.3.5 (new):** Three consecutive runs hit F.3.1–F.3.4 without any wedged-job failure. A transient Pro-call timeout that durably surfaces as `status='failed'` (Defect 6 fix) does NOT count as a pass — the run must complete. If Run 2 fails on a Vertex transient, the counter resets to zero and the 60-min time-box continues; this is the Phase 6.5 §8 behaviour, preserved.

#### §6.4.3.1 — F.3.1 budget re-baseline (Phase 6.8, 2026-05-25)

F.3.1's 180s acceptance was set against the Phase 6.6 latency math but observed
runs landed at 214s on a cold stack (job c0a66106e65c44978f967fe94618be44 in
the V5 halt, then ~210-215s consistently across the V3/V4/V5 attempts that
got far enough to complete normalize). The 30-35s overshoot is attributable
to cold-cache variance in the Vertex Pro ensemble — the first ~5 Pro calls
of a fresh session pay gRPC channel setup + IAM Credentials.signBlob warm-up.

Re-baseline:
- F.3.1 acceptance: completes under **240s** wall-clock (was 180s).
- Target / aspirational: 180s on a warm stack (post first run).
- Tightening per-lane ensemble timeout was considered and rejected — it
  would raise the EnsembleError rate on legitimate slow Pro calls and re-
  pollute the failure-status story Phase 6.6 §6.3 just stabilized.

The Master PRD §3.3 narrative timing is updated to "in about three to four
minutes" for honesty about cold-stack wall-clock.

### §6.5 — Master PRD §3.3 Update

**Current §3.3 paragraph.** References the K+N scenario as a 50-lane spot rate book demonstration. Build agent: locate the existing paragraph (Phase 6.5 left it intact) and replace with the text below.

**New §3.3 paragraph (single replacement, ≤120 words):**

> *"The Magic Moment scenario uses a 15-lane K+N-style spot rate book — `K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` — that exhibits the same surface-level messiness as a real forwarder's quarterly tariff: mixed port-code formats (clean UN/LOCODE alongside obfuscated city names), three merged-cell rate-tier headers, ~50 columns with surcharge tabs and free-text carrier notes, prose-format effective and expiry dates, and three deliberately embedded validation triggers — an impossible UN/LOCODE entry, a negative rate value, and an expired tariff window. Solvo's Onramp processes the file end-to-end in under three minutes, surfacing eleven normalized lanes, one to two flagged for human review with citation-grounded clarification text, and two deterministically rejected with rule-ID provenance."*

§3.4 (system map) and §5 (execution spec / voiceover language from the Path-1 routing patches) are NOT touched.

### §6.6 — `PHASE_6_5_SPEC.md` §6.2 Supersession Note

**Append a §6.2.1 subsection immediately after the existing §6.2 body in `PHASE_6_5_SPEC.md`.** Do NOT delete or rewrite existing Phase 6.5 content.

**Exact text to append (≤6 lines):**

```markdown
#### §6.2.1 — Superseded by PHASE_6_6_SPEC §6.4 (2026-05-21)

The K+N fixture above (50 lanes) was shrunk to 15 lanes in Phase 6.6 (commit
landing post-`c24710b`) to fit the recalibrated F.3.1 acceptance budget
(90 s → 180 s). Broken-lane positions moved from (23, 31, 47) to (7, 11, 14).
See `PHASE_6_6_SPEC.md` §6.4.1 for the new fixture contract and §6.4.3 for
the revised acceptance criteria.
```

### §6.7 — `tests/integration/test_pipeline_e2e.py` Updates

**Two changes:**

1. **Happy-path test (existing).** The test currently asserts the 3-lane benchmark from PHASE_6_5_SPEC §6.4 (commit `1a75c21`). Update to drive `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` (the new 15-lane version) and assert:
   - Job reaches `status='completed'` within 200 s (a 20 s margin above the 180 s F.3.1 budget so the test isn't flaky on cold caches).
   - `OnrampOutput.lane_count` is 9–13.
   - `OnrampOutput.flagged_count` is 0–3.
   - `OnrampOutput.rejected_count` is 1–3.
   - Exactly one `audit_log` row with `stage='validated'`.
   - Exactly one `slack_post` row with non-empty `payload.blocks`.

2. **Defect 6 regression test (new).** Add a test named `test_normalize_failure_surfaces_as_status_failed`:
   - Submits a job against a fixture that the test environment can force into a normalize-time failure. Two acceptable mechanisms (build agent picks one):
     - **(a)** Use the existing `broken_negative_rates.xlsx` fixture and patch `packages.ingest.normalizer.normalize_lanes` to raise `EnsembleError("simulated Pro-call timeout for regression test")` deterministically.
     - **(b)** Submit the 15-lane K+N fixture against a worker with an env-var-injected `SOLVO_FORCE_ENSEMBLE_FAIL_AT_LANE_INDEX=3` test hook that raises `EnsembleError` on the chosen lane.
   - Asserts:
     - The job reaches `status='failed'` within 60 s of submission.
     - `OnrampJob.completed_at` is non-null.
     - Exactly one `OnrampOutbox` row with `event_type='audit_log'` AND `payload.stage='normalize_failed'`.
     - That payload's `error_type` is `"EnsembleError"`.
     - That payload's `error_message` is non-empty and contains no `/tmp/onramp/` substring (PII redaction holds).
   - The test is gated by the existing `SOLVO_RUN_E2E_TESTS=1` flag and runs against the running compose stack.

The build agent picks mechanism (a) unless it discovers a reason (a) breaks. Document the choice in a one-line code comment at the top of the test.

---

## §7 — Cross-Phase Integration Requirements

Phase 6.6 must NOT break:

- **Phase 6.5 per-task engine pattern.** `make_async_engine` per Celery task with `finally: await engine.dispose()` stays in `_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once`, and `archive_completed_jobs`. The Defect 6 fix is layered on top — the failure-path transaction is opened from the same `factory` derived from the same per-task engine, before `engine.dispose()` runs in the outer `finally`.
- **Phase 6.5 `slack_post` outbox enqueue.** Still fires from `_validate`'s success path. Failure path explicitly does NOT enqueue a `slack_post` row (Defect 6 fix preserves this; failure has its own `audit_log` row, no Slack notification).
- **Phase 6.5 `_recover_requested_slack_channel` helper.** Still reads from the `ingress_received` audit_log outbox row. Phase 6.6 does not touch the intake route or the helper.
- **Transactional-outbox invariant.** Success-path: outbox rows + job-state update commit in one transaction. Failure-path: failure-status row + failure audit_log row commit in their own one transaction. The two paths are mutually exclusive.
- **§3.10 compliance posture.** Vertex calls still route via `location='global'` (Path-1). Cloud Run + GCS stay europe-west4. Models pinned to `gemini-3.1-flash-lite` / `gemini-3.1-pro-preview`. Zero-retention configuration unchanged.
- **Anti-Replication boundary.** No new code paths touch pricing, POMDP/Bayesian RL, value iteration, or market-clearing logic. Phase 6.6 is pure infrastructure / fixture / narrative work.
- **Redis distributed lock pattern.** `SET key value NX EX <seconds>` unchanged; dispatcher's `_drain_once` is not touched.
- **N=3 ensemble at temperatures (0.1, 0.5, 0.9), majority-vote consensus.** Locked invariants from Phase 3. Phase 6.6's only ensemble-related change is documenting the per-lane parallelism contract that's already in code; the build agent does NOT modify `_ensemble_for_lane`.

---

## §8 — Phase 6.6 Acceptance Criteria

Step 3B advances to `BUILD_COMPLETE_V3.md` (final close) only when ALL of the following are true:

1. **`docker-compose.yml` has the shared staging volume.** `docker compose config | grep -A 2 "staging:"` shows the named volume declared AND mounted at `/tmp/onramp` on both `api` and `worker` services.
2. **`packages/compliance/vertex_client.py` has no module-level cache.** `git grep "_client_cache" packages/compliance/vertex_client.py` returns zero matches; `get_vertex_client` is a thin per-call constructor.
3. **All three failure paths use the option-(b) pattern.** Static inspection of `_extract`, `_normalize`, `_validate` in `packages/ingest/tasks.py` shows the failure-handler in its own `async with factory() as <name>_session, <name>_session.begin():` block, distinct from the success-path transaction. The `raise` follows the `enqueue_outbox_event(... "audit_log" ...)` call.
4. **`_failure_payload` helper exists.** In `packages/ingest/tasks.py`. Tested indirectly via the Defect 6 regression test.
5. **`fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` is the new 15-lane version.** `openpyxl.load_workbook(...).active.max_row` returns 18 (header + 15 data rows + 3 merged-tier rows) or close. The three broken lanes are at indices 7, 11, 14 of the data-row sequence.
6. **Fixture determinism preserved.** Running `python data/_generate.py` twice in a clean checkout produces byte-identical SHA-256s for all four demo fixtures.
7. **`Solvo_Master_PRD.md` §3.3 reflects the 15-lane narrative.** Grep for "15-lane" returns a hit in §3.3. Grep for "50-lane" returns zero hits in §3.3 (it may still appear in historical sections; that's fine).
8. **`PHASE_6_5_SPEC.md` §6.2.1 supersession note appended.** The §6.2 body is untouched; the new §6.2.1 subsection sits immediately after.
9. **`tests/integration/test_pipeline_e2e.py` updated.** Happy-path test runs against the 15-lane fixture with the new count bands. New `test_normalize_failure_surfaces_as_status_failed` test exists and is gated by `SOLVO_RUN_E2E_TESTS=1`.
10. **Pre-existing unit tests still pass.** `pytest tests/unit -q` returns ≥148 passing (no regression from Phase 6.5).
11. **Lint clean.** `ruff check .` returns 0 findings.
12. **Type-checking clean on changed files.** `mypy --strict` on `packages/ingest/tasks.py packages/compliance/vertex_client.py data/_generate.py tests/integration/test_pipeline_e2e.py` returns 0. The pre-existing 6 `mypy` errors in `packages/compliance/retention.py` (introduced in `dfaf079`, out-of-scope per Phase 6.5 approval) remain unaddressed.
13. **Secret scan clean.** `gitleaks detect --no-banner --no-git --source .` returns zero findings; visual inspection of the Phase 6.6 diff confirms no new secrets land.
14. **Final Stage F.3-F.5 re-run readiness.** After Step 3A builds and Step 3B reviews Phase 6.6, a single re-run of Stages F.3-F.5 (Magic Moment × 3 against the 15-lane K+N fixture under the 180 s budget; broken fixtures; audit-trail verification) is the next gate. Phase 6.6 acceptance does NOT require running F.3-F.5; that's the post-approval validation.

---

## §9 — Explicit NON-GOALS for Phase 6.6

- **No worker-process-resident-loop refactor for the Vertex client.** Per-call construction is the production-grade temporary; the deeper refactor is post-engagement work.
- **No lane-level parallelism.** Lanes stay sequential. Per-lane ensemble parallelism is sufficient. Bursting N=3 × 15 = 45 concurrent Pro requests would hit Vertex burst-rate limits and complicate the architectural story.
- **No new Postgres tables, no migrations.** Migration head stays `0004_intake_review`.
- **No PRD §5 voiceover changes.** Path-1 routing language preserved verbatim from commit `98030d2`.
- **No new fixtures.** Only the K+N file shrinks; the three broken fixtures stay byte-identical to their Phase 6.5 versions.
- **No `packages/compliance/retention.py` mypy cleanup.** The 6 pre-existing errors from the Stage F.2 Vertex SDK fallback (commit `dfaf079`) remain out-of-scope and are tracked separately.
- **No deletion of `HUMAN_INTERVENTION_REQUEST_V2.md`.** It stays as the historical record of the second F.3 halt.
- **No Stage F.3-F.5 execution as part of Phase 6.6 acceptance.** F.3-F.5 re-runs after Phase 6.6 review approval.
- **No `BUILD_COMPLETE_V2.md` modification.** Phase 6.6 closure produces `BUILD_COMPLETE_V3.md`; V2 is preserved as the Phase 6.5 closure historical record.
- **No `PHASE_7_SPEC.md`.** Sprint 2 ends at Phase 6.6 close.
- **No `_recover_requested_slack_channel` refactor.** The Phase 6.5 recovery-via-convention pattern stays as-is.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_6_SPEC.md`. They are historical. Only `PHASE_6_5_SPEC.md` receives the §6.2.1 supersession note.
- Do NOT touch `BUILD_COMPLETE.md` or `BUILD_COMPLETE_V2.md`. Both are historical closure records.
- Do NOT rename `apps/worker/celery_app.py`, `packages/ingest/tasks.py`, `packages/dispatcher/outbox_worker.py`, or `packages/compliance/vertex_client.py`. Adjust their internals only.
- Do NOT introduce a worker-process-resident asyncio loop (out of scope; deserves its own phase).
- Do NOT add a second event-loop layer (anyio bridges, trio, etc.). Celery + `asyncio.run` + per-task engine + per-task Vertex client is the Phase 6.6 shape.
- Do NOT modify the §3.10.4 audit_log shape beyond adding the `error_type` / `error_message` fields under the `*_failed` payload stages. The success-path `audit_log` payloads stay byte-identical to Phase 6.5.
- Do NOT introduce new env vars in the production code path. The Defect 6 regression test MAY use a test-only env hook (`SOLVO_FORCE_ENSEMBLE_FAIL_AT_LANE_INDEX`), in which case the env var is read only when `pytest` is running (gated by a module-level `if os.environ.get("PYTEST_CURRENT_TEST"):` guard or equivalent), never in production.
- Do NOT commit any fixture larger than 100 KB. The 15-lane K+N fixture should land around ~5–8 KB (smaller than the Phase 6.5 50-lane version at ~10 KB). If the actual size exceeds the cap, halt and report — likely an openpyxl style-bloat issue.
- Do NOT modify the Phase 6.5 review-patch invariants on `data/_generate.py:_save_demo_workbook` (the `dcterms:modified` regex rewrite + sorted-member zip rewrite must remain in place).

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`.
- All Vertex AI calls bind to `location='global'` (Path-1 routing) with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation (dev permissive on ZDR enrollment, production requires `VERTEX_AI_ZDR_ENROLLED=true`).
- Container-boot validators fail-fast on misconfiguration (the four from §3.10).
- Anti-Replication boundary: no pricing, no POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing logic, no rate / margin / recommendation computation.
- Transactional outbox: success-path outbox rows commit in the same transaction as the job-state update. **Phase 6.6 carve-out:** failure-path outbox rows commit in a separate transaction from the success path; the failure-row write and the failure-status write are atomic with respect to each other.
- Redis distributed locks use `SET NX EX` pattern (not Redlock, not WATCH/MULTI).
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus stays exactly as Phase 3 shipped; per-lane parallelism via `asyncio.gather` stays exactly as Phase 3 shipped.
