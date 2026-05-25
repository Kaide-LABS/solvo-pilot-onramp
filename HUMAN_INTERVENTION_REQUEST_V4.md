# HUMAN INTERVENTION REQUEST V4 — Step 4 Stage F.3 re-run HALTED again (post Defect 10 IAM grant)

**Date:** 2026-05-25
**Halting agent:** Claude Code (Step 4 Stage F.3 smoke runner, resumed after Defect 10 IAM grant)
**Repo HEAD at halt:** commit landing this V4 + the Defect 10 SDK-call-shape patch (`packages/storage/signed_url.py`)
**Stage status at halt:** F.1 PASSED, F.2 PASSED, **F.3 Run 1 PARTIAL PASS** (pipeline completed `status='completed'` at 169 s — F.3.1 budget met, validate path proved working), **but two new defect classes (11, 12) block F.3.2 / F.3.3 verification.**

The IAM grant Hafeedh applied was correct and necessary. It was not sufficient. The google-cloud-storage Python SDK does NOT auto-detect that the local OAuth credentials should route signing through the IAMCredentials.signBlob API — the caller must explicitly pass `access_token=...` alongside `service_account_email=...`. The V3 writeup's claim that "the signed_url.py code already passes service_account_email; with this role grant the local OAuth will sign successfully" was wrong about SDK behaviour. The follow-up code patch is documented in §1 and committed alongside this V4.

After that patch, **F.3 Run 1 completed end-to-end** (validate signed the result URL and committed the slack_post outbox row). That's the proof point that Defect 10 is genuinely closed. But Run 1 then surfaced two more defect classes:

---

## §1 — Defect 10 Final Resolution (committed in this drop)

The SDK call shape needed `access_token=creds.token` AND a `credentials=creds` explicit argument so that:
- `storage.Client` uses fresh creds (rather than ADC-default re-discovery)
- `blob.generate_signed_url(..., service_account_email=..., access_token=...)` triggers the IAMCredentials.signBlob path

Patch (committed):

```diff
     def _sync() -> tuple[str, datetime]:
+        import google.auth
+        import google.auth.transport.requests
         from google.cloud import storage  # type: ignore[attr-defined]

         from packages.core.settings import get_settings

-        client = storage.Client(project=get_settings().gcp_project_id)
+        creds, _ = google.auth.default(
+            scopes=["https://www.googleapis.com/auth/cloud-platform"]
+        )
+        creds.refresh(google.auth.transport.requests.Request())
+
+        client = storage.Client(project=get_settings().gcp_project_id, credentials=creds)
         blob = client.bucket(bucket).blob(blob_name)
         issued_at = datetime.now(UTC)
         url: str = blob.generate_signed_url(
             version="v4",
             expiration=timedelta(seconds=ttl_seconds),
             method="GET",
             service_account_email=service_account,
+            access_token=creds.token,
         )
         return url, issued_at + timedelta(seconds=ttl_seconds)
```

**Verification:** F.3 Run 1 (job `e5b82d509633426e9e8f5b81cbd59a65`) completed at 169 s wall-clock, status='completed'. The validate stage successfully signed the GCS URL and committed both `audit_log/validated` and `slack_post` outbox rows. The IAM grant + SDK-call-shape patch together are sufficient.

---

## §2 — Defect 11 (BLOCKING) — Slack dispatcher fails with `unhashable type: 'Settings'`

**Symptom:** Run 1 completed and the `slack_post` outbox row was enqueued correctly, but the worker's `drain_outbox` task fails on every retry:

```
worker-1 | [14:25:19] WARNING dispatch outbox_id=40 event=slack_post attempt=1 failed: unhashable type: 'Settings'
worker-1 | [14:25:54] WARNING dispatch outbox_id=40 event=slack_post attempt=2 failed: unhashable type: 'Settings'
worker-1 | [14:26:29] WARNING dispatch outbox_id=40 event=slack_post attempt=3 failed: unhashable type: 'Settings'
worker-1 | [14:31:34] WARNING dispatch outbox_id=40 event=slack_post attempt=4 failed: unhashable type: 'Settings'
```

**Likely root cause:** Somewhere in the Slack-post dispatcher path (`packages/dispatcher/handlers/` or `packages/slack/`), a function decorated with `@lru_cache` (or `functools.cache`) is being called with a `Settings` instance. `Settings` (Pydantic `BaseSettings`) is not hashable by default and raises `TypeError: unhashable type: 'Settings'`. This is the **same hazard pattern Phase 6.6 fixed for `get_vertex_client`** (per-call construction to avoid module-level cache) — but the Slack path was not audited as part of Phase 6.6 §6.2 because the spec scoped Defect 5 narrowly to Vertex.

**Why it didn't surface earlier:** Same masking chain as Defects 8-10 — `_validate` never previously reached the `slack_post` enqueue (Phase 6.5 fixed `slack_post` enqueue but no F.3 run had previously completed to the point where dispatcher had a row to consume).

**Fix surface (not applied — Claude Code halting per Step 4 prompt rule "Defect 11+ → HALT"):**
- Grep `packages/` and `apps/` for `@lru_cache` and `@functools.cache` decorators on functions taking `Settings`. Replace with explicit per-call construction OR cache by a hashable key (e.g., `settings.id` if such exists, or specific scalar fields).
- Cross-reference against the Slack post path: `packages/dispatcher/outbox_worker.py:_drain_once` → `packages/dispatcher/handlers/slack.py` (or similar) → `packages/slack/client.py` (or wherever `WebClient` / `chat_postMessage` is constructed).
- Verify the fix locally with a single dispatcher drain tick before retrying F.3.

This appears to be a real (mostly-rename) bug not a config issue; likely a Phase 7-style "closure patch v3" or direct ops commit.

---

## §3 — Defect 12 (BLOCKING) — `/v1/intake/jobs/{job_id}/result-url` returns 500

**Symptom:** After Run 1 completed, fetching the result URL returns 500:

```
api-1 | sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.
api-1 |   File "/app/apps/api/routes/intake.py", line 195, in get_result_url
api-1 |     async with session.begin():
```

**Root cause:** The `get_result_url` route handler uses `async with session.begin():` against a FastAPI-injected session whose dependency has already opened a transaction. The route should either:
- (a) drop the explicit `session.begin()` and rely on the dependency's transaction, OR
- (b) ensure the dependency yields an idle session (no transaction).

This is **independent from Defect 10** — the patched signed-URL code path inside this route runs only if the transaction context succeeds. With the transaction error, signing never executes.

**Why it didn't surface earlier:** No F.3 run had previously reached the point where a result-URL fetch made sense. Phase 6's `tests/integration/test_pipeline_e2e.py` happy-path test calls a different result-fetch path (it reads from `OnrampOutput` directly via the DB, not through `/result-url`).

**Fix surface (not applied):** Likely a one-line removal of `async with session.begin():` in `apps/api/routes/intake.py:195` after confirming the dependency-injected session already provides transactional scope (the standard FastAPI + SQLAlchemy async pattern). Audit other route handlers in `apps/api/routes/` for the same pattern.

---

## §4 — F.3 Run 1 Partial Evidence (despite Defects 11/12)

Run 1 (job `e5b82d509633426e9e8f5b81cbd59a65`) achieved the following — this is real evidence that the core pipeline works post-Defect-10:

| Check | Result |
|---|---|
| F.3.1 — runtime under 180 s | ✅ 169 s |
| F.3.2 — output counts in 9-13/0-3/1-3 bands | ⏸ blocked by Defect 12 (result-url 500) — counts present in DB but not surfaced via the API. Direct DB inspection of `onramp_outputs.lane_count/flagged_count/rejected_count` would unblock this. |
| F.3.3 — outbox has audit_log(validated) AND slack_post | ✅ both rows present in `onramp_outbox`; `audit_log/validated` delivered=true. `slack_post` delivered=false due to Defect 11 (4 retries, all `unhashable type: 'Settings'`). |
| F.3.3.b — slack_post delivered within 5-10 s | ❌ blocked by Defect 11 |

Outbox state for the Run 1 job:

```
 event_type |      stage       | delivered
------------+------------------+-----------
 audit_log  | ingress_received | t
 audit_log  | extracted        | t
 audit_log  | normalized       | t
 audit_log  | validated        | t
 slack_post |                  | f  (attempts=4, all failed with unhashable Settings)
```

This is good news: Phase 6.6's `_failure_payload` / `_commit_failure` / per-task engine / per-call Vertex client all remained intact (visible across Run 1's normalize at 145 s, validate at 1.8 s). The remaining blockers are 100% in adjacent code paths the Phase 6.6 spec did not scope.

---

## §5 — Cost Incurred During This Resumed Run

Two F.3 attempts of Run 1 in this resumed session:
- Attempt 1 (pre-SDK-shape patch): completed normalize, failed validate → ~50 Pro calls (15 lanes × 3) + 1 Flash.
- Attempt 2 (post-SDK-shape patch): completed end-to-end → ~50 Pro calls + 1 Flash + any clarification/correction Pro calls (typically 0-2 for this fixture).

Approx. 100 Pro + 2 Flash calls ≈ **$0.20-$0.30 of Vertex spend** in this run, on top of the ~$0.50 from the prior halt. **Cumulative Sprint-2-smoke spend: ~$0.70-$0.80.**

---

## §6 — Stage F.4 and F.5 Status

Not attempted. Both depend on F.3 fully passing. F.5 specifically depends on a successful F.3 job to query for audit entries.

---

## §7 — Decision Tree for Next Iteration

**Path A (minimal):** Apply the Defect 11 + Defect 12 patches as direct ops commits (analogous to the Defect 8/9 patches in commit `ace72d6`). Restart F.3 Run 1 from a clean stack. Likely 30 min of work + 3 × ~170 s F.3 runs + F.4 + F.5.

**Path B (formal):** Write `PHASE_6_7_SPEC.md` covering Defects 8-12, run Step 3A build + Step 3B review, then retry F.3-F.5. Several hours of overhead with no functional change beyond Path A.

Recommendation: **Path A.** The Phase 6.6 closure's spec scope (Defects 4-7) was explicitly bounded; the surfacing of Defects 8-12 is a consequence of every prior smoke run halting before validate could complete. Treating them as ops fixes rather than a new spec cycle is the correct read of intent.

Concrete next steps for Hafeedh (Path A):
1. Grep for `@lru_cache` / `@functools.cache` on functions taking `Settings`. Fix the Slack-path occurrence. Common location guess: `packages/slack/client.py` or `packages/dispatcher/handlers/slack.py`.
2. Open `apps/api/routes/intake.py:195` `get_result_url`. Remove the `async with session.begin():` wrapper if the dependency-injected session already has transactional scope.
3. Commit as `fix: Defects 11 + 12 — Slack Settings caching + result-url session transaction`.
4. `docker compose down -v && docker compose build worker api dispatcher && docker compose up -d --wait`.
5. Run migrations + reference data loaders.
6. Restart F.3 Run 1 from scratch.
7. If F.3 then passes on 3 consecutive runs, proceed to F.4 + F.5 and write `BUILD_COMPLETE_V4.md`.

If a Defect 13 surfaces during the next F.3 attempt, halt with V5. The escalation is real — we've now uncovered five pre-existing defects (8-12) that survived all six phases plus two closures because no F.3 run had previously reached the post-normalize / dispatcher / result-fetch surface. Each one was masked by the next-upstream failure.

---

## §8 — Sprint-Level Implication

`BUILD_COMPLETE_V3.md` was committed honestly: Phase 6.6 §8 acceptance criteria all passed on code-merit. The newly-surfaced defects (8-12) are NOT regressions of Phase 6.6; they are pre-existing surface area that became visible only because Phase 6.6's fixes let the pipeline run far enough to exercise them. Phase 6.6 itself remains closed and the eight defects called out in V3 remain genuinely closed.

The actionable claim from V3 — "demo recording un-blocked, pending F.3-F.5 re-run" — was premature in retrospect. F.3-F.5 are now demonstrably non-trivial and the smoke surface is wider than the V3 author (myself, as halting agent) anticipated. V3's optimism was a mistake.

— End of HUMAN_INTERVENTION_REQUEST_V4.md.
