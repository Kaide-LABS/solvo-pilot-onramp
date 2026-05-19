# PHASE 5 SPEC — Solvo Pilot Onramp Sprint 2

**Output of Step 3B (Phase 4 review approved, Phase 5 blueprinted).** Consumes: `ULTIMATE_PRD.md` §3.6 (Slack interface), §3.7 (signed-URL delivery), §3.10.4 (audit trail), `Solvo_Master_PRD.md` §5 (operator-grade `/v1/intake/*`), `PHASE_4_SPEC.md` §6.6 (validate_output_task wiring carry-forward — see §7 below). Feeds: Step 3A (Codex build of Phase 5) → Step 3B (review + advance to Phase 6 spec).

---

## §0 — PHASE PLAN HEADER

**This is Phase 5 of 6 phases in the Sprint 1 build.** Phase 4 (EDIFACT + Stage 4 rules + audit trail) was approved at SHA `e6a86fa`. Phase 6 closes the sprint with Cloud Run deployment + `BUILD_COMPLETE.md`.

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 | 0–8 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake. |
| ✅ Phase 2 | 8–20 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor. |
| ✅ Phase 3 | 20–28 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load. |
| ✅ Phase 4 | 28–36 | EDIFACT, Stage 4 rules engine, audit trail, `/internal/v1/audit`. |
| **Phase 5** | 36–48 | **Slack app (Block Kit summary + slash command `/solvo-onramp` + mention handler), `POST /v1/webhooks/slack`, operator-grade `/v1/intake/jobs` + `/v1/intake/jobs/{id}` + `/v1/intake/jobs/{id}/result-url` + `/v1/intake/jobs/{id}/review`, signed Cloud Storage URL delivery, outbox dispatcher worker, Phase 4 wiring carry-forward (conformal + correction + clarification into `validate_output_task`).** |
| Phase 6 | 48–60 | Cloud Run europe-west4 of 3 services, Cloud SQL + Memorystore, 7-day GCS lifecycle, 90-day archive job, 9-criterion acceptance suite, `BUILD_COMPLETE.md`. |

---

## §1 — FILES ADDED OR MODIFIED

**Added:**

```
apps/api/routes/
├── intake.py                      # /v1/intake/jobs (operator-grade ingress)
└── slack.py                       # /v1/webhooks/slack (Slack Events + slash + mention)

packages/slack/
├── __init__.py
├── client.py                      # AsyncWebClient singleton
├── signing.py                     # X-Slack-Signature HMAC verification (deterministic)
├── block_kit.py                   # NormalizedRatesheet → Block Kit summary builder
└── handlers.py                    # slash command + mention dispatch

packages/storage/
├── __init__.py
├── signed_url.py                  # GCS V4 signed-URL generator (deterministic, idempotent)
└── upload.py                      # blob upload helper (Phase 5 staging → GCS bucket)

packages/dispatcher/
├── __init__.py
├── outbox_worker.py               # outbox dispatcher: drains onramp_outbox rows
└── delivery.py                    # per-event-type delivery: slack_post, signed_url_create,
                                   # webhook_callback, audit_log (audit_log is no-op deliver)

packages/core/models/
├── intake.py                      # IntakeJobRequest, IntakeJobResponse, ReviewAck
└── slack.py                       # SlackSlashCommand, SlackEventEnvelope, SlackPostResult

tests/unit/
├── test_slack_signing.py          # HMAC verification + replay window
├── test_block_kit.py              # summary builder output shape
├── test_slack_handlers.py         # slash + mention dispatch
├── test_intake_routes.py          # all four /v1/intake endpoints
├── test_signed_url.py             # signed URL generation idempotency
├── test_outbox_worker.py          # at-least-once + idempotency-lock semantics
├── test_intake_models.py          # strict-forbid coverage
└── test_validate_wiring.py        # Phase 4 wiring carry-forward: conformal + correction +
                                   # clarification all execute inside validate_output_task

migrations/versions/
└── 0004_intake_review.py          # onramp_intake_reviews (operator review acks)
```

**Modified:**

- `packages/ingest/tasks.py` — `validate_output_task` extended to: (1) call `compute_conformal_score` per surviving lane using EnsembleVote rows now persisted into `onramp_conformal_scores`; (2) gate-trigger `conditional_correction` when consensus rolled into Phase 4 with `requires_review=True`; (3) draft `clarification` for each `FlaggedLane`. All in the same transaction as the audit_log row.
- `packages/ingest/normalizer.py` — persist per-lane `EnsembleVote` + `ConsensusResult` into `onramp_conformal_scores` so Phase 5's `validate_output_task` has data to compute conformal scores from. (Spec §1 of Phase 4 listed this; not implemented in Phase 4. Carried forward.)
- `apps/api/main.py` — mount `intake_routes` at `/v1/intake` and `slack_routes` at `/v1/webhooks/slack`.
- `apps/worker/celery_app.py` — register the outbox-dispatcher beat schedule (every 5 s).
- `packages/core/settings.py` — `expected_alembic_head = "0004_intake_review"`; add `slack_signing_secret`, `slack_bot_token`, `gcs_bucket_outputs`, `gcs_signer_service_account`.
- `packages/ingest/outbox.py` — `OutboxEventType` Literal stays the same (Phase 4 already added `access_log`).
- `apps/api/routes/jobs.py` — emit an `access_log` outbox row in the same transaction as each `/v1/jobs/{id}/status` and `/v1/jobs/{id}/result` SELECT (carry-forward of audit invariant from Phase 4).
- `CHANGELOG.md` — Phase 5 entry.

---

## §2 — PIP DEPENDENCIES

```toml
"slack_sdk>=3.34,<4",              # AsyncWebClient + signing verifier
"google-cloud-storage>=2.18,<3",   # signed-URL generation + blob upload
```

Both are first-class GCP / Slack SDKs with py.typed markers — no mypy override expansion needed. `docs/modernization_log.md` §12 must be updated in the same PR.

---

## §3 — PYDANTIC SCHEMAS (Phase 5)

### 3.1 `packages/core/models/intake.py`

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class IntakeJobRequest(BaseModel):
    """Operator-grade ingress (form-encoded multipart, separate from /v1/ingest)."""

    model_config = ConfigDict(extra="forbid")

    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    operator_email: str = Field(min_length=5, max_length=128)
    requested_slack_channel: str = Field(min_length=2, max_length=128)
    priority: Literal["normal", "rush"] = "normal"


class IntakeJobResponse(BaseModel):
    """202 body returned by POST /v1/intake/jobs."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["pending", "extracting", "normalizing", "validating", "completed", "failed"]
    submitted_by: str = Field(min_length=5, max_length=128)
    submitted_at: datetime


class ReviewAck(BaseModel):
    """Operator acknowledgment of a flagged lane outcome."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    lane_id: str
    decision: Literal["accept", "reject", "needs_prospect_clarification"]
    operator_email: str = Field(min_length=5, max_length=128)
    notes: str = Field(default="", max_length=512)
    acknowledged_at: datetime


class SignedUrlResponse(BaseModel):
    """Body returned by GET /v1/intake/jobs/{id}/result-url."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    url: str = Field(min_length=64, max_length=2048)
    expires_at: datetime
```

### 3.2 `packages/core/models/slack.py`

```python
class SlackSlashCommand(BaseModel):
    """Slack slash-command form-encoded body."""

    model_config = ConfigDict(extra="forbid")

    token: str
    team_id: str
    channel_id: str
    user_id: str
    command: Literal["/solvo-onramp"]
    text: str = Field(default="", max_length=512)
    response_url: str = Field(min_length=8, max_length=512)
    trigger_id: str


class SlackEventEnvelope(BaseModel):
    """Slack Events API envelope (mention + url_verification)."""

    model_config = ConfigDict(extra="forbid")

    token: str
    team_id: str | None = None
    api_app_id: str | None = None
    type: Literal["event_callback", "url_verification"]
    challenge: str | None = None
    event: dict[str, Any] | None = None


class SlackPostResult(BaseModel):
    """Slack post acknowledgement persisted into the outbox payload."""

    model_config = ConfigDict(extra="forbid")

    channel: str
    ts: str                                        # Slack message timestamp (idempotency key)
    job_id: str
    posted_at: datetime
```

---

## §4 — FASTAPI ROUTE SIGNATURES (Phase 5)

### 4.1 `POST /v1/webhooks/slack` (`apps/api/routes/slack.py`)

```python
@router.post(
    "",
    responses={200: {}, 401: {}, 403: {}, 422: {}},
)
async def slack_webhook(
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...),
) -> JSONResponse:
    """Verify X-Slack-Signature HMAC + 5-minute replay window before parsing.

    Routes:
      type=url_verification → echo challenge.
      type=event_callback   → dispatch to handlers.handle_mention.
      command=/solvo-onramp → dispatch to handlers.handle_slash.
    """
```

- Signature verification uses `hmac.compare_digest` against
  `v0:{timestamp}:{raw_body}` per Slack docs. Replay window: ±300 s.
- Failures: 401 (signature mismatch), 403 (replay window exceeded), 422 (body
  cannot be parsed against `SlackSlashCommand` / `SlackEventEnvelope`).

### 4.2 `POST /v1/intake/jobs` (`apps/api/routes/intake.py`)

```python
@router.post(
    "",
    response_model=IntakeJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {}, 422: {}},
)
async def submit_intake_job(
    request: IntakeJobRequest = Depends(parse_form_request),
    upload: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> IntakeJobResponse:
    """Operator ingress. Equivalent to /v1/ingest/ratesheet but with priority
    + operator_email provenance. Same SHA-256 idempotency on input bytes."""
```

### 4.3 `GET /v1/intake/jobs/{job_id}` — `IntakeJobResponse` 200/404
### 4.4 `GET /v1/intake/jobs/{job_id}/result-url` — `SignedUrlResponse`, 200/404/409
### 4.5 `GET /v1/intake/jobs/{job_id}/review` — `list[ReviewAck]` 200/404
### 4.6 `POST /v1/intake/jobs/{job_id}/review` — `ReviewAck` 201/404/422

- `result-url` returns 409 when status != "completed". Signed URL valid for **15 minutes**, V4-signed by the service-account configured in `Settings.gcs_signer_service_account`.
- Review endpoint writes one row into `onramp_intake_reviews` AND one `audit_log` outbox event (`action="review_acknowledged"`) in the same transaction.

Routes NOT in Phase 5 (deferred):
- Cloud Run-specific health/readiness wiring — Phase 6.

---

## §5 — ALEMBIC MIGRATION (`migrations/versions/0004_intake_review.py`)

```python
revision = "0004_intake_review"
down_revision = "0003_audit_trail"


def upgrade() -> None:
    op.create_table(
        "onramp_intake_reviews",
        sa.Column("review_id",      sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", sa.Text,
            sa.ForeignKey("onramp_jobs.job_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lane_id",        sa.Text, nullable=False),
        sa.Column("decision",       sa.Text, nullable=False),
        sa.Column("operator_email", sa.Text, nullable=False),
        sa.Column("notes",          sa.Text, nullable=False, server_default=""),
        sa.Column(
            "acknowledged_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("job_id", "lane_id", name="uq_intake_review_one_per_lane"),
    )
    op.create_index("ix_intake_review_job", "onramp_intake_reviews", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_intake_review_job", table_name="onramp_intake_reviews")
    op.drop_table("onramp_intake_reviews")
```

**Settings change:** `expected_alembic_head = "0004_intake_review"`.

---

## §6 — IMPLEMENTATION LOGIC FLOW

### 6.1 Slack Signature Verification (`packages/slack/signing.py`)

**Pure-Python, deterministic, zero LLM.**

```python
def verify_signature(
    *, secret: str, body: bytes, timestamp: str, signature: str
) -> Literal[True]:
    """Raise SlackSignatureError on mismatch / replay; return True on pass.

    1. Reject if abs(now() - timestamp) > 300 seconds (replay window).
    2. Compute v0:{timestamp}:{body} HMAC-SHA256 with `secret`.
    3. hmac.compare_digest against `signature`.
    """
```

### 6.2 Block Kit Summary (`packages/slack/block_kit.py`)

`NormalizedRatesheet` → Block Kit JSON blocks. **Never includes raw rate values** beyond the count summary — Anti-Replication invariant restated. The summary shows lane count, flagged count, rejected count, and the first three flagged-lane reasons. Raw rates are linked via the signed URL, not embedded.

### 6.3 Signed URL (`packages/storage/signed_url.py`)

```python
async def generate_v4_signed_url(
    *, bucket: str, blob_name: str, ttl_seconds: int = 900,
    service_account: str,
) -> tuple[str, datetime]:
    """Return (signed_url, expires_at). V4 signing via google-cloud-storage."""
```

- TTL pinned to **900 s (15 min)**.
- Idempotency: the call is pure (no side effects). The outbox dispatcher records the issued URL into a `signed_url_create` event for audit.
- The signing service account is loaded from `Settings.gcs_signer_service_account` (a workload-identity binding in Cloud Run; Phase 6 wires the actual binding).

### 6.4 Outbox Dispatcher (`packages/dispatcher/outbox_worker.py`)

```python
@celery_app.task(name="tasks.dispatcher.drain_outbox", bind=True, max_retries=0)
def drain_outbox_task(self) -> dict[str, int]:
    """Drain all rows with delivered_at IS NULL AND (next_retry_at IS NULL OR
    next_retry_at <= now()). For each row, acquire Redis lock and dispatch.
    """
```

**Hard requirements:**

- Redis lock pattern: `SET solvo:onramp:outbox:{outbox_id} {worker_uuid} NX EX 30`. **Not Redlock, not WATCH/MULTI.**
- Successful deliveries: set `delivered_at=now()` and clear `next_retry_at`. Failures: exponential backoff (5s → 30s → 5m → 30m → 2h → 24h, then stop with `attempts >= 6`).
- Per-event-type idempotency:
  - `slack_post`: keyed by `(channel, thread_ts, job_id)`. Slack returns the same `ts` for duplicate posts within the channel + thread; we accept this and record the `ts` from Slack's reply.
  - `signed_url_create`: pure-function; idempotency by construction.
  - `audit_log`: write-only into the dispatcher's own log; no external side-effect.
  - `access_log`: same.
  - `webhook_callback`: idempotency key = `(job_id, event_type, payload_hash)`; sent as `X-Idempotency-Key` header.
- Beat schedule registers `drain_outbox_task` to run every 5 s.

### 6.5 Phase 4 Wiring Carry-Forward (`packages/ingest/tasks.py`)

`validate_output_task` extended to:

```python
async def _validate(job_id: str) -> None:
    # ... existing rules_engine call ...

    # Phase 5 carry-forward: read EnsembleVote rows persisted by Phase 5's
    # extended normalizer.py, compute conformal score per surviving lane.
    votes_by_lane = await load_votes_by_lane(session, job_id)
    calibration = load_calibration(Path("fixtures/conformal_calibration_v1.json"))
    conformal_by_lane: dict[str, ConformalScore] = {
        lane.lane_id: compute_conformal_score(lane.lane_id, votes_by_lane[lane.lane_id], calibration)
        for lane in validated.lanes
        if lane.lane_id in votes_by_lane
    }
    low_confidence = [
        FlaggedLane(lane=lane, reason="low_confidence", confidence=cf.confidence)
        for lane in validated.lanes
        if (cf := conformal_by_lane.get(lane.lane_id)) is not None and not accepts(cf)
    ]

    # Gate-trigger conditional correction for prior no-majority cases.
    corrected_flags: list[FlaggedLane] = []
    for flagged in validated.flagged_for_review:
        if flagged.reason == "no_majority":
            prior_consensus = await load_consensus(session, job_id, flagged.lane.lane_id)
            corrected = await conditional_correction(prior_consensus, settings)
            if corrected.consensus_lane is None:
                corrected_flags.append(flagged)  # still no majority
            # else: lane is now resolved; surface it back into validated.lanes.

    # Draft clarification text for each remaining flagged lane.
    clarifications: dict[str, str] = {
        f.lane.lane_id: await draft_clarification(f, settings)
        for f in (corrected_flags + low_confidence)
    }

    # All side effects below land in the same session.begin() block:
    #  - onramp_outputs upsert with the post-conformal/post-correction payload
    #  - onramp_conformal_scores write
    #  - audit_log row (action="validate_complete", payload includes
    #    conformal_summary + clarifications)
```

Phase 5's `normalizer.py` upstream extension persists per-lane `EnsembleVote` and `ConsensusResult` JSON into `onramp_conformal_scores.ensemble_votes` so `_validate` has the inputs.

### 6.6 Slash Command and Mention Handlers (`packages/slack/handlers.py`)

- `/solvo-onramp status <job_id>` — looks up status, posts ephemeral Block Kit response.
- `/solvo-onramp upload` — returns ephemeral instruction text (uploads still go through `/v1/intake/jobs`; Slack file uploads are Phase 6 stretch).
- Mention (`@solvo-onramp help`) — posts the help text.

All Slack outbound calls go through the outbox (write `slack_post` event → dispatcher delivers). **No direct synchronous Slack POST from a request handler.**

---

## §7 — CROSS-PHASE INTEGRATION REQUIREMENTS

### 7.1 Phase 4 wiring carry-forward (load-bearing)

PHASE_4_SPEC §6.6 promised `validate_output_task` would run rules_engine + conformal + correction + clarification. The Phase 4 implementation shipped only rules_engine. The three orphan modules pass their isolated unit tests but have zero production callers. **Phase 5 closes this gap.**

The wiring requires:
1. `normalizer.py` extension to persist per-lane `EnsembleVote` + `ConsensusResult` into `onramp_conformal_scores.ensemble_votes` (PHASE_4_SPEC §1 listed this; Phase 4 did not implement it).
2. New `packages/core/db/repositories.py` helpers: `load_votes_by_lane`, `load_consensus`.
3. `validate_output_task` body extension as sketched in §6.5.
4. `test_validate_wiring.py` proves the full chain runs: a synthetic job with a no-majority lane drives conformal scoring, triggers correction, drafts clarification, and writes everything in one transaction.

This carry-forward must land in Phase 5 — Phase 6 cannot deploy without it.

### 7.2 Other invariants preserved

- **Boot validators.** `expected_alembic_head` bumps to `0004_intake_review`.
- **Anti-Replication.** Block Kit summary shows lane counts + flagged reasons only; never raw rates. Clarification post-processor still rejects digits. Signed URLs link to the JSON output, not to a rate-recommendation surface.
- **Transactional outbox.** Every Phase 5 route side-effect (slack_post enqueue, signed_url_create, access_log, audit_log) writes through `enqueue_outbox_event` in the caller's transaction. The dispatcher worker is the *only* place that hits external systems.
- **Redis distributed locks.** Dispatcher uses `SET key value NX EX seconds`. No Redlock multi-instance, no WATCH/MULTI.
- **Vertex AI client singleton.** Unchanged; Phase 5 introduces no new LLM call sites.

---

## §8 — PHASE 5 ACCEPTANCE CRITERIA

1. **Migration head:** `alembic upgrade head` lands at `0004_intake_review`; downgrade succeeds.
2. **Slack signature verification:** `test_slack_signing.py` covers (a) valid signature passes, (b) mismatched signature 401, (c) timestamp outside ±300 s window 403.
3. **Block Kit summary contains no raw rates:** `test_block_kit.py` asserts the rendered JSON has no key matching `base_rate_usd` or surcharge amounts. Only counts + reasons + signed URL.
4. **Intake routes:** `test_intake_routes.py` covers all four endpoints (POST jobs, GET status, GET result-url, GET reviews, POST review) including 409 for not-completed result-url.
5. **Signed URL TTL pinned:** `test_signed_url.py` asserts `expires_at = generated_at + 900 s` exactly.
6. **Outbox dispatcher:** `test_outbox_worker.py` asserts (a) `SET key value NX EX seconds` lock pattern; (b) exponential backoff schedule; (c) per-event-type idempotency.
7. **Phase 4 wiring closed:** `test_validate_wiring.py` constructs a synthetic job where Phase 3 normalize_lanes_task produced a no-majority consensus and asserts that `validate_output_task` (a) computes conformal scores from persisted EnsembleVote rows, (b) calls `conditional_correction` exactly once for the no-majority lane, (c) drafts clarification text via `draft_clarification`, (d) commits all side effects in one transaction.
8. **Audit-log emission:** every operator-grade route action writes an `onramp_audit_log` row with the correct `action` literal (`ingress_received`, `review_acknowledged`, `result_delivered`).
9. **Anti-Replication grep:** `rg -i -e 'recommend' -e 'predict.*price' -e 'pomdp' -e 'value_iter' -e 'constrained.*mdp' -e 'active.*learning' -e 'belief.*state' -e 'margin' packages/ apps/` returns zero matches.
10. **Determinism grep:** `rg "generate_content" packages/slack/ packages/storage/ packages/dispatcher/` returns zero matches. Slack, storage, dispatcher are pure-Python.
11. **No direct Slack POST from request handlers:** `rg "client.chat_postMessage|WebClient.*post|\.aio\.chat_post" apps/api/routes/` returns zero matches. All Slack output flows through the outbox.
12. **Lint and types:** `ruff check .` returns 0; `mypy --strict packages/core packages/compliance packages/ingest packages/reference packages/slack packages/storage packages/dispatcher apps/api` returns 0. Coverage on changed code ≥ 80%.
13. **Secret scan:** `gitleaks detect --no-banner --no-git --source .` zero findings.
14. **Phase 1–4 regression:** all prior unit tests pass unchanged.

---

## §9 — EXPLICIT NON-GOALS FOR PHASE 5

The executor MUST NOT implement the following in Phase 5:

- **No Cloud Run deploy / Cloud SQL / Memorystore provisioning.** Phase 6.
- **No production GCS bucket creation.** Phase 5 uses an emulator (`fake-gcs-server`) or test-bucket env var; real bucket creation lives in Phase 6 terraform/gcloud scripts.
- **No 7-day storage lifecycle rules / 90-day archive job.** Phase 6.
- **No widening of the Phase 3 N=3 ensemble or the Phase 4 N=2 correction temperatures.** The (0.1, 0.5, 0.9) and (0.0, 1.0) triples remain locked.
- **No new LLM call sites.** Slack handlers, storage, and the dispatcher are pure-Python. The only LLM calls in the project after Phase 5 are: Stage 2 Excel/EDIFACT extraction (Flash), Stage 3 N=3 normalization (Pro), Phase 4 conditional correction N=2 (Pro), Phase 4 clarification phrasing (Pro). Phase 5 adds nothing here.
- **No Slack file upload as ingress path.** Slash command directs the operator to the existing `/v1/intake/jobs` HTTP route. Slack-native file ingress is Phase 6 stretch.
- **No webhook outbound to non-Slack endpoints.** `webhook_callback` outbox event type is plumbed but the dispatcher's webhook delivery is gated behind a `Settings.enable_webhook_callbacks: bool = False`. Phase 6 may enable it.
- **No POMDP, no Bayesian RL, no value iteration, no Constrained MDP, no belief-state inference, no active learning on booking outcomes, no price/rate/margin/recommendation/market-clearing logic.** (Anti-Replication invariant — restated for Phase 5.)
- **No raw rate embedding in Slack messages.** Block Kit summary may show lane counts, flagged-lane reasons, and clarification questions — never a numeric rate. The signed URL is the only delivery surface for rate data.

---

*End of Phase 5 Spec. Next: Step 3A executes against this spec to produce code; Step 3B reviews and emits `PHASE_6_SPEC.md`.*
