# PHASE 6.8 SPEC — Third Closure Patch

**Output of Step 2 (Phase 6.8 spec generation).** Consumes the Step 4 Stage F.3 re-run halt at commit `9bb5bd5` (`HUMAN_INTERVENTION_REQUEST_V5.md`), the live state of the codebase at that commit (including the V3/V4 direct-ops fixes at `ace72d6`, `6d3ed3f`, `99453a1`), and Phase 6.6's §6.4.3 latency math. Feeds a single Step 3A build cycle, a single Step 3B review cycle, then a final Stage F.3-F.5 smoke pass. After Phase 6.8 lands and F.3-F.5 passes, Sprint 2 closure is final.

---

## §0 — Phase Plan Header

**This is Phase 6.8 of the Sprint 1 build — a third closure patch following the Step 4 Stage F.3 re-run halt at commit `9bb5bd5` (HUMAN_INTERVENTION_REQUEST_V5.md). Phase 6.5 closed Defects 1-3. Phase 6.6 closed Defects 4-7. Direct ops commits (`ace72d6`, `6d3ed3f`, `99453a1`) closed Defects 8-12. Phase 6.8 closes Defects 13 + 14 and re-baselines the F.3.1 acceptance budget. After Phase 6.8 lands and F.3-F.5 passes, Sprint 2 closure is final.**

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 – 6 | Sprint 2 build | Scaffolding through Cloud Run deployment. |
| ✅ Phase 6.5 | post-F.3 halt #1 | Defects 1-3 (Celery engine, fixtures, slack_post enqueue). |
| ✅ Phase 6.6 | post-F.3 halt #2 | Defects 4-7 (staging volume, Vertex client cache, failure handler, fixture shrink + budget). |
| ✅ Direct ops (V3+V4) | post-V3 + V4 halts | Defects 8-12 (Dockerfile COPY, storage project arg, IAM-API signing, Slack lru_cache, result-url tx). |
| **Phase 6.8** | post-F.3 halt #3 (V5) | **Defects 13 + 14 + F.3.1 budget re-baseline.** |

**Scope:**

- **Defect 13** — `aiohttp` missing in `pyproject.toml` dependencies. `slack_sdk.web.async_client.AsyncWebClient.chat_postMessage` requires it at runtime; the dispatcher's `slack_post` delivery raises `ModuleNotFoundError: No module named 'aiohttp'` on every retry.
- **Defect 14** — `_validate` never uploads the normalized JSON to GCS. The `/v1/intake/jobs/{job_id}/result-url` endpoint signs a URL for `gs://<gcs_bucket_outputs>/jobs/<job_id>/normalized_ratesheet.json`, but nothing in the pipeline ever writes that blob. `curl` against the signed URL returns 404.
- **F.3.1 budget re-baseline** — 180s → 240s. Phase 6.6 §6.4.3's 180s math assumed warm-cache Vertex latency; observed cold-stack runs land at ~210-215s. The 180s target remains aspirational; 240s is the new acceptance ceiling.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 6.8.** Per ULTIMATE_PRD §4.7, provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 6.8 introduces no new academic claims — it is pure bug-fix and outbox-wiring work.

---

## §1 — Files Added or Modified

**Modified:**

- `pyproject.toml` — **MODIFIED**. Add `aiohttp>=3.9.0` to top-level project dependencies. (Defect 13.)
- `packages/ingest/outbox.py` — **MODIFIED**. Add `"upload_result"` to the `OutboxEventType` `Literal[...]`.
- `packages/ingest/tasks.py` — **MODIFIED**. `_validate`'s success-path transaction enqueues a new `upload_result` outbox row alongside the existing `audit_log/validated` + `slack_post` rows. All three commit in the same `session.begin()` block. Failure path unchanged (no upload_result on failure).
- `packages/dispatcher/delivery.py` — **MODIFIED**. Add `deliver_upload_result(payload, settings)` handler. Mirrors the shape of the existing `deliver_slack_post`.
- `packages/dispatcher/outbox_worker.py` — **MODIFIED**. Add the `elif event_type == "upload_result":` dispatch branch alongside the existing slack_post / webhook_callback / signed_url_create / audit_log / access_log branches. Import `deliver_upload_result`.
- `packages/storage/upload.py` — **NEW**. Provides `async def upload_normalized_json(bucket, blob_name, payload, content_type) -> None` using the same `google.auth.default()` + `creds.refresh()` + explicit `credentials=creds` pattern as `signed_url.py`. Per-call construction; no module-level cache.
- `PHASE_6_6_SPEC.md` — **MODIFIED**. Append a §6.4.3.1 subsection re-baselining F.3.1 from 180s to 240s (≤8 lines). Existing §6.4.3 body unchanged.
- `Solvo_Master_PRD.md` §3.3 — **MODIFIED**. Update narrative timing from "in under three minutes" to "in about three to four minutes". One paragraph touch.
- `tests/integration/test_pipeline_e2e.py` — **MODIFIED**. Happy-path test extended to fetch the `/result-url` response, GET the signed URL with backoff (3 attempts × 2s spacing to absorb the upload_result outbox drain race), and parse the result JSON. Asserts count bands match the Phase 6.6 §6.4.3 ranges (9-13 normalized / 0-3 flagged / 1-3 rejected).

**Added:**

- `packages/storage/upload.py` (per above).

**Deleted:** none. HUMAN_INTERVENTION_REQUEST_V3.md, V4.md, V5.md, and BUILD_COMPLETE_V3.md remain on disk as the historical record. They are NOT modified by Phase 6.8.

> **Note on the failure path:** `_validate`'s except-block (added in Phase 6.6 §6.3) does NOT enqueue an `upload_result` row on failure. The failure-handler enqueues only `audit_log/validate_failed`, by design — there is no normalized JSON to upload if validate failed. Phase 6.6's separate-transaction failure handler contract is unchanged.

---

## §2 — Pip Dependencies

**One new top-level dependency:**

```toml
[project]
dependencies = [
    # ... existing dependencies preserved verbatim ...
    "aiohttp>=3.9.0",
]
```

`slack_sdk` lists `aiohttp` under its `[async]` extras group, which pip does not resolve transitively when `slack_sdk` is installed without the extras suffix. The Phase 5 scope did not catch this because no F.3 run had previously delivered a `slack_post` outbox row. **Do NOT** instead install `slack_sdk[async]` — adding `aiohttp` directly is more transparent and avoids pulling unrelated slack_sdk extras.

Dispatcher and worker images both need the rebuild. The api image does not import `slack_sdk` and can be left alone (though rebuilding it for consistency is acceptable; no other code change in this phase needs the api image rebuilt).

---

## §3 — Pydantic Schemas

**No new schemas.** The JSON written to GCS is `OnrampOutput.normalized_payload` (a JSONB column already storing a Pydantic-serialized `NormalizedRatesheet` via `model_dump(mode="json")` in `_validate`). Phase 6.8 reads that column verbatim and uploads it. No envelope wrapper. No metadata schema beyond the GCS object's own `Content-Type: application/json` + `Cache-Control: no-cache, max-age=0`.

---

## §4 — FastAPI Route Signatures

**No route changes.** Both `/v1/intake/jobs/{job_id}/result-url` (Defect 12 fix landed at `99453a1`) and the underlying `signed_url.py` (Defect 10 fix landed at `6d3ed3f`) are untouched. Phase 6.8 only needs the blob to exist when `curl` fetches the signed URL; the signing path itself already works.

---

## §5 — Alembic Migration

**No migration.** `OutboxEventType` is a Python-side `Literal` — `OnrampOutbox.event_type` is a `text` column with no DB-side enum. Adding `"upload_result"` to the Literal does not require a migration.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 13 Fix: `aiohttp` Dependency

**Problem (precise).** `slack_sdk.web.async_client.AsyncWebClient.chat_postMessage` constructs an `aiohttp.ClientSession` lazily on first use. The slack_sdk package's setup.py declares `aiohttp` only under `extras_require={"async": [...]}`. When pip installs `slack_sdk` without the `[async]` qualifier (as the current pyproject.toml does), `aiohttp` is not installed. The first `chat_postMessage` call raises `ModuleNotFoundError: No module named 'aiohttp'`.

**Fix (precise).** Add `aiohttp>=3.9.0` to top-level `pyproject.toml` dependencies. Rebuild dispatcher + worker images (the worker hosts the Celery `drain_outbox` task that runs `deliver_slack_post`).

**Version pin reasoning.** `aiohttp>=3.9.0` is the floor for Python 3.13 compatibility (current worker / dispatcher / api base image is Python 3.13). No upper pin — slack_sdk's `[async]` extras already pin a permissive range. Test under `pytest tests/unit -q` post-install to confirm no transitive conflicts.

### §6.2 — Defect 14 Fix: GCS Upload via Outbox Event

#### §6.2.1 — Architectural Decision

The transactional outbox pattern is the right shape. `_validate` enqueues `upload_result` alongside the existing `audit_log/validated` and `slack_post` rows in one atomic `session.begin()` block. The dispatcher's `drain_outbox` loop (already running every 5s) picks up `upload_result` and writes the blob to GCS.

**Why the outbox and not a direct upload from `_validate`:**
- The outbox keeps the upload retriable (the dispatcher already has retry-with-attempts semantics).
- GCS write latency (~100-300ms) does NOT extend the `_validate` task wall-clock — the upload lands shortly after `_validate` commits.
- If the upload retries fail, the job stays `status='completed'` (the database state is correct — normalization succeeded). Audit_log captures upload failures separately. The pre-computed signed URL in the `slack_post` blob will 404 for the duration of the failure window.

**Race condition (accepted).** The `slack_post` outbox row contains the signed URL, computed BEFORE the upload_result row is drained. If a user clicks the URL between dispatcher ticks (≤5s window), they get a transient 404. The integration test absorbs this with a 3-attempt × 2s-spacing retry against the signed URL. This is the Phase 6.8 demo-grade contract; a stricter gating (Slack post depends on upload success) would deserve its own spec.

#### §6.2.2 — Outbox Event Wiring

`packages/ingest/outbox.py` — append `"upload_result"` to the `OutboxEventType` Literal:

```python
OutboxEventType = Literal[
    "slack_post",
    "webhook_callback",
    "audit_log",
    "signed_url_create",
    "access_log",
    "upload_result",   # NEW (Phase 6.8 §6.2)
]
```

`packages/ingest/tasks.py` — inside `_validate`'s success-path `session.begin()` block, alongside the existing `audit_log/validated` + `slack_post` enqueues:

```python
await enqueue_outbox_event(
    session,
    job_id=job_id,
    event_type="upload_result",
    payload={
        "bucket": settings.gcs_bucket_outputs,
        "blob_name": f"jobs/{job_id}/normalized_ratesheet.json",
    },
)
```

Order within the block: `audit_log/validated` → `slack_post` → `upload_result`. The order doesn't matter for correctness (single transaction commit) but keeps audit-trail visual scanning consistent.

The `_validate` failure-handler (Phase 6.6 §6.3) does NOT enqueue `upload_result`.

#### §6.2.3 — Dispatcher Handler

`packages/dispatcher/delivery.py` — add `deliver_upload_result`. Mirrors the existing `deliver_slack_post` shape:

```python
async def deliver_upload_result(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Upload OnrampOutput.normalized_payload as JSON to gs://<bucket>/<blob_name>.

    Phase 6.8 (§6.2.3). Reads the normalized payload from Postgres via a per-task
    AsyncEngine (Phase 6.5 invariant), serializes it as canonical JSON
    (sort_keys=True, ensure_ascii=False), and uploads via packages.storage.upload.

    payload contract:
        - job_id (str)        — injected by outbox_worker dispatch
        - bucket (str)        — settings.gcs_bucket_outputs at enqueue time
        - blob_name (str)     — "jobs/<job_id>/normalized_ratesheet.json"

    Returns a dispatch-result dict for the outbox row's delivered_at audit.
    """
    import json

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from packages.core.db.base import OnrampOutput
    from packages.core.db.session import make_async_engine
    from packages.storage.upload import upload_normalized_json

    job_id = payload["job_id"]
    bucket = payload["bucket"]
    blob_name = payload["blob_name"]

    engine = make_async_engine(settings)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            result = await session.execute(
                select(OnrampOutput.normalized_payload).where(
                    OnrampOutput.job_id == job_id
                )
            )
            normalized = result.scalar_one_or_none()
        if normalized is None:
            raise ValueError(f"job {job_id!r} has no normalized_payload to upload")

        payload_bytes = json.dumps(
            normalized, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")

        await upload_normalized_json(
            bucket=bucket,
            blob_name=blob_name,
            payload=payload_bytes,
            content_type="application/json",
        )
        return {
            "uploaded": True,
            "blob_name": blob_name,
            "size_bytes": len(payload_bytes),
        }
    finally:
        await engine.dispose()
```

**Invariants preserved:**
- Per-task `make_async_engine` + `engine.dispose()` in `finally` (Phase 6.5 §6.1).
- No module-level cache, no shared client across forks (Phase 6.6 §6.2).
- Pure read against `OnrampOutput.normalized_payload` — no transactional outbox writes from this handler. The handler's "success" signal back to the dispatcher is the dict return value; the dispatcher itself stamps `delivered_at` and increments `attempts` on the original `OnrampOutbox` row.

#### §6.2.4 — `outbox_worker.py` Dispatch Branch

`packages/dispatcher/outbox_worker.py` — at the existing `if event_type == ...` chain (currently slack_post / webhook_callback / signed_url_create / audit_log / access_log), add the upload_result branch. Suggested ordering: place it adjacent to `signed_url_create` (both touch GCS):

```python
from packages.dispatcher.delivery import (
    deliver_slack_post,
    deliver_upload_result,   # NEW
    # ... existing imports ...
)

# ... inside the dispatch table ...
elif event_type == "upload_result":
    await deliver_upload_result(payload, settings)
```

The `job_id` is injected into the `payload` dict by the existing `outbox_worker.py` dispatch flow (it reads `OnrampOutbox.job_id` and merges it into the payload before passing — verify against the current code; if it doesn't, the handler signature should explicitly take `job_id` as a kwarg). The build agent SHOULD verify the dispatch shape against `deliver_slack_post`'s actual call signature in `outbox_worker.py` and align.

#### §6.2.5 — Upload Function

`packages/storage/upload.py` (NEW file):

```python
"""GCS upload helper. Implements PHASE_6_8_SPEC.md §6.2.5.

Mirrors packages/storage/signed_url.py's credential pattern: per-call
google.auth.default() + creds.refresh() with explicit credentials=creds on
the storage.Client. Required because the local-compose worker's ADC is
user OAuth (no private key); the IAMCredentials.signBlob path used by
signed_url is irrelevant here (we're uploading, not signing), but the
explicit project + credentials pair is still the production-grade shape.
"""

from __future__ import annotations

import asyncio


async def upload_normalized_json(
    *,
    bucket: str,
    blob_name: str,
    payload: bytes,
    content_type: str = "application/json",
) -> None:
    """Upload `payload` to gs://<bucket>/<blob_name>."""

    def _sync() -> None:
        import google.auth
        import google.auth.transport.requests
        from google.cloud import storage  # type: ignore[attr-defined]

        from packages.core.settings import get_settings

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())

        client = storage.Client(
            project=get_settings().gcp_project_id, credentials=creds
        )
        blob = client.bucket(bucket).blob(blob_name)
        blob.cache_control = "no-cache, max-age=0"
        blob.upload_from_string(payload, content_type=content_type)

    await asyncio.to_thread(_sync)
```

**Why `Cache-Control: no-cache, max-age=0`:** the V4 signed URL TTL is 900s (§3.10.3). If the operator re-runs the job within the TTL, the same `blob_name` (`jobs/<job_id>/normalized_ratesheet.json`) would otherwise serve a stale cached copy. With `no-cache`, intermediate caches must re-validate. The blob itself is overwritten atomically by GCS on each upload.

**No retry inside `upload_normalized_json`** — the outbox dispatcher already has retry-with-attempts semantics. Adding inner retry would compound the retry window.

#### §6.2.6 — GCS Write Permission (HAFEEDH ACTION)

The worker's local ADC needs `roles/storage.objectAdmin` (or at minimum `roles/storage.objectCreator`) on the output bucket.

**REQUIRED before Step 3A build:**

```bash
gcloud storage buckets add-iam-policy-binding gs://kaide-solvo-onramp-dev-staging \
  --member="user:sharedkaide.io@gmail.com" \
  --role="roles/storage.objectAdmin"
```

(Replace the bucket name with the actual `gcs_bucket_outputs` value from `.env` if different. The user account is the same one that received the `iam.serviceAccountTokenCreator` grant for Defect 10.)

Production Cloud Run is unaffected — the workload-identity-bound SA already has `roles/storage.objectAdmin` on the outputs bucket via the existing Terraform config (`infra/terraform/iam.tf` or equivalent). Verify by reading the Terraform IAM module; if absent, file as a separate post-engagement IAM cleanup item.

**If the IAM grant is not in place when Step 3A runs the build:** Defect 14 will surface a NEW failure mode on the dispatcher's upload retries (`google.api_core.exceptions.Forbidden: 403 ... does not have storage.objects.create access`). This would be a Defect 15, not a regression of Phase 6.8 — but it would block F.3 sign-off until the grant lands.

### §6.3 — F.3.1 Budget Re-Baseline

Append to `PHASE_6_6_SPEC.md` immediately after the existing §6.4.3 body:

```markdown
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
```

Do NOT rewrite the existing §6.4.3 body; only append §6.4.3.1.

Update `Solvo_Master_PRD.md` §3.3 — replace the phrase `"in under three minutes"` (or whatever the exact text Phase 6.6 wrote) with `"in about three to four minutes"`. Single-paragraph change.

### §6.4 — Integration Test Hardening

`tests/integration/test_pipeline_e2e.py` happy-path `test_kn_15_lane_reaches_completed_and_emits_slack_post`: extend after the existing status=`completed` assertion to fetch the signed URL and parse the result JSON.

Sketch (the build agent picks the precise shape against the actual test fixtures):

```python
import asyncio
import httpx

# ... existing assertions on status, counts, outbox ...

# Phase 6.8 §6.4: fetch the signed URL via the result-url endpoint, then
# GET the URL itself and parse the result JSON. Retries absorb the
# upload_result outbox drain race (Phase 6.8 §6.2.1).
async with httpx.AsyncClient(base_url=_API_BASE) as client:
    result_url_response = await client.get(f"/v1/intake/jobs/{job_id}/result-url")
    assert result_url_response.status_code == 200
    signed_url = result_url_response.json()["url"]

async with httpx.AsyncClient() as gcs_client:
    last_status = None
    for _attempt in range(3):
        blob_response = await gcs_client.get(signed_url)
        last_status = blob_response.status_code
        if last_status == 200:
            break
        await asyncio.sleep(2.0)
    assert last_status == 200, (
        f"GCS blob not uploaded after 3 × 2s retries (signed URL fetch "
        f"returned {last_status}); upload_result outbox drain may be stuck"
    )

result = blob_response.json()
assert 9 <= len(result["lanes"]) <= 13
assert 0 <= len(result["flagged_for_review"]) <= 3
assert 1 <= len(result["deterministically_rejected"]) <= 3
```

The retry budget (3 × 2s = 6s) is sized against the dispatcher's 5s drain tick, with one extra tick for the actual upload (~300ms) plus jitter. If the upload genuinely fails, all 3 retries will see the same 404 and the assertion fails — exactly the Defect 14 surface the test is designed to lock in.

**The Defect 6 regression test (`test_normalize_failure_surfaces_as_status_failed`) is NOT touched.** Failure-path doesn't enqueue `upload_result`, so the test's assertions remain valid.

---

## §7 — Cross-Phase Integration Requirements

Phase 6.8 must NOT break:

- **Phase 6.5 per-task `make_async_engine` pattern.** The new `deliver_upload_result` handler uses it. No module-level engine.
- **Phase 6.6 per-call `get_vertex_client`.** Orthogonal — the upload path does not touch Vertex.
- **Phase 6.6 `_failure_payload` / `_commit_failure` shape.** `_validate`'s failure-handler does NOT enqueue `upload_result`. Success path adds the enqueue inside the existing `session.begin()` block; structure unchanged.
- **Phase 6.5 `slack_post` outbox enqueue.** Still fires from `_validate`'s success path. The signed URL inside the slack_post payload is now backed by an actual GCS blob (post upload_result drain).
- **Phase 6.5 `_recover_requested_slack_channel` helper.** Phase 6.8 does not touch the intake route or the helper.
- **Transactional outbox invariant.** Success-path now commits FOUR outbox rows + the `status='completed'` update in one transaction (audit_log/validated, slack_post, upload_result, and — if the result-url endpoint has been hit — audit_log/result_delivered, but that one is a separate route-handler write). Failure-path still commits the failure rows in their own fresh transaction.
- **§3.10 retention posture.** Vertex calls still route via `location='global'`. Cloud Run + GCS stay europe-west4. Models pinned. Zero-retention configuration unchanged. The GCS object's lifecycle policy on the outputs bucket is unchanged by this spec (it inherits the existing bucket-level retention class set in Terraform).
- **Anti-Replication boundary.** No pricing, POMDP, MDP/CMDP, value iteration, market-clearing, active-learning, or margin-recommendation code introduced. Phase 6.8 is pure dispatch + GCS upload + dep-add + budget-re-baseline work.
- **Redis distributed lock pattern.** `SET NX EX` unchanged.
- **N=3 ensemble at (0.1, 0.5, 0.9), majority-vote consensus, per-lane parallelism.** Untouched.

---

## §8 — Phase 6.8 Acceptance Criteria

3A build + 3B review approve when ALL true:

1. **`pyproject.toml` includes `aiohttp>=3.9.0`.** Inspect the deps array; `grep "aiohttp" pyproject.toml` returns a hit.
2. **`packages/ingest/outbox.py` `OutboxEventType` includes `"upload_result"`.** Static inspection of the Literal.
3. **`_validate` success-path enqueues four artifacts in one transaction.** Static inspection of `packages/ingest/tasks.py:_validate`: inside the success-path `async with factory() as session, session.begin():` block, the calls are: (a) OnrampOutput upsert, (b) update_job_status → "completed", (c) `enqueue_outbox_event(... event_type="audit_log", payload={"stage": "validated", ...})`, (d) `enqueue_outbox_event(... event_type="slack_post", ...)`, (e) `enqueue_outbox_event(... event_type="upload_result", payload={"bucket": ..., "blob_name": ...})`. Failure-path unchanged (still only the failure audit_log row, in its own fresh transaction).
4. **`packages/dispatcher/delivery.py` has `deliver_upload_result`** matching §6.2.3, with per-task engine + finally-disposal.
5. **`packages/dispatcher/outbox_worker.py` dispatches `upload_result`.** Inspect the `if/elif` chain.
6. **`packages/storage/upload.py` exists** with `upload_normalized_json` matching §6.2.5 (per-call creds.refresh, Cache-Control: no-cache, explicit project+credentials on Client).
7. **`tests/integration/test_pipeline_e2e.py` happy-path fetches signed URL + parses JSON** with the 3 × 2s retry per §6.4.
8. **`PHASE_6_6_SPEC.md` §6.4.3.1 supersession note appended.** Existing §6.4.3 body unchanged.
9. **`Solvo_Master_PRD.md` §3.3 narrative timing updated** from "under three minutes" to "about three to four minutes".
10. **`pytest tests/unit -q` passes 148+ tests.** No regression from the dep add or the outbox event-type expansion.
11. **`ruff check .` clean.**
12. **`mypy --strict` clean on changed files** (`packages/ingest/tasks.py packages/ingest/outbox.py packages/dispatcher/delivery.py packages/dispatcher/outbox_worker.py packages/storage/upload.py tests/integration/test_pipeline_e2e.py`). The 6 pre-existing `packages/compliance/retention.py` errors remain out-of-scope per PHASE_6_6_SPEC §9.
13. **No new secrets in the diff.** `gitleaks detect --no-banner --no-git --source .` zero findings.
14. **Stage F.3-F.5 re-run readiness.** Post-approval validation. Phase 6.8 acceptance does NOT require running F.3-F.5; that's the next gate.

---

## §9 — Explicit NON-GOALS for Phase 6.8

- **No `BUILD_COMPLETE_V4.md` written by Phase 6.8 itself.** That lands after F.3-F.5 actually passes against the Phase 6.8 stack.
- **No Terraform changes.** The output-bucket IAM grant for the local-dev OAuth principal is a manual gcloud command (§6.2.6); production already has the workload-identity-bound SA writeable via existing IaC.
- **No `retention.py` mypy cleanup.** Still out of scope.
- **No `slack_sdk[async]` extras swap.** Adding `aiohttp` directly is the cleaner contract.
- **No Slack-post-gates-on-upload-success refactor.** The race condition documented in §6.2.1 is accepted for the V1 demo; gating would deserve its own spec.
- **No ensemble timeout tightening.** F.3.1 budget is re-baselined, not the underlying latency math.
- **No new Pydantic schemas.** The GCS payload is the existing `OnrampOutput.normalized_payload` JSONB column verbatim.
- **No deletion of HUMAN_INTERVENTION_REQUEST_V3.md, V4.md, or V5.md.** All three remain on disk as the historical halt record.
- **No `PHASE_6_9_SPEC.md`.** Sprint 2 ends at Phase 6.8 close + F.3-F.5 pass.
- **No `_recover_requested_slack_channel` refactor.** The Phase 6.5 recovery-via-convention pattern stays.
- **No fixture regeneration.** The 15-lane K+N fixture from Phase 6.6 §6.4.1 is unchanged. The three broken fixtures are unchanged.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_6_SPEC.md`, or `PHASE_6_5_SPEC.md`. Only `PHASE_6_6_SPEC.md` receives the §6.4.3.1 supersession note.
- Do NOT touch `BUILD_COMPLETE.md`, `BUILD_COMPLETE_V2.md`, or `BUILD_COMPLETE_V3.md`. They are historical closure records.
- Do NOT touch the V3, V4, or V5 intervention-request files. They are historical halt records.
- Do NOT rename `apps/worker/celery_app.py`, `packages/ingest/tasks.py`, `packages/dispatcher/outbox_worker.py`, `packages/dispatcher/delivery.py`, `packages/compliance/vertex_client.py`, or `packages/storage/signed_url.py`. Adjust their internals only.
- Do NOT modify the §3.10.4 audit_log shape. The new `upload_result` payload is NOT an audit_log — it's its own event type.
- Do NOT introduce a new env var. The bucket and blob_name come from `settings.gcs_bucket_outputs` (already wired) and from a deterministic format string.
- Do NOT introduce inner retry logic in `upload_normalized_json`. The outbox dispatcher handles retries.
- Do NOT add `slack_sdk[async]` to dependencies — add `aiohttp` directly.
- Do NOT install `aiohttp` in only one Dockerfile. The `pyproject.toml` change cascades through all three image builds via `pip install .` (or whatever the actual install command is in each Dockerfile). Verify by inspecting one of the three Dockerfiles' install line; if any of them pin-installs deps separately, fail the build agent and re-spec.

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`.
- All Vertex AI calls bind to `location='global'` (Path-1 routing) with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation.
- Container-boot validators fail-fast on misconfiguration (the four from §3.10).
- Anti-Replication boundary: no pricing, POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing, no rate / margin / recommendation computation.
- **Transactional outbox**: success-path outbox rows commit in the same transaction as the job-state update — Phase 6.8 expands this to FOUR rows (audit_log/validated + slack_post + upload_result + the implicit OnrampOutput upsert). Failure-path outbox rows commit in a separate transaction (Phase 6.6 §6.3).
- Redis distributed locks use `SET NX EX`.
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus stays exactly as Phase 3 shipped; per-lane parallelism via `asyncio.gather` stays exactly as Phase 3 shipped.
- Per-task `make_async_engine` (Phase 6.5) preserved across `_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once`, `archive_completed_jobs`, AND the new `deliver_upload_result`.
- Per-call `get_vertex_client` (Phase 6.6) preserved.
- Deterministic Stage 1 + Stage 4 — zero LLM calls in `classify_format` or the rules engine.

— End of PHASE_6_8_SPEC.md.
