# SOLVO PILOT ONRAMP — BUILD COMPLETE V2 (post Phase 6.5 closure)

**Sprint 2 final close.** This document supplements `BUILD_COMPLETE.md` (which recorded the six-phase Phase 6 close at SHA `69a757e`). Phase 6.5 — a closure patch following the Stage F.3 smoke-test halt — has now landed, fixing three defects that blocked end-to-end pipeline execution under Celery and made Stage F.3–F.5 smoke un-runnable.

`BUILD_COMPLETE.md` is preserved as the historical Phase 6 close artifact. This file is the closure record after Phase 6.5.

---

## §1 — PHASE 6.5 LEDGER

| Artifact | SHA |
|---|---|
| Spec — `PHASE_6_5_SPEC.md` | `060a5c9` |
| Implementation — `feat: Phase 6.5 implementation (Sprint 2)` | `1a75c21` |
| Fix patches — `fix: Phase 6.5 review patches (Sprint 2)` | `518232d` |
| Approval — `chore: Phase 6.5 review approved (Sprint 2)` | `3b35e17` |
| Closure — this file | pending on the `docs: Sprint 2 build complete (post Phase 6.5 closure)` commit |

Sprint 2 phases approved: 6 + closure patch 6.5. **Sprint terminates here.** No PHASE_7 spec follows; subsequent engagement-side work (Procurement Lens at month 2, etc.) starts a fresh sprint cadence per PHASE_6_5_SPEC §9.

---

## §2 — DEFECTS FIXED IN PHASE 6.5

Three defects (named verbatim from `PHASE_6_5_SPEC.md` §0):

1. **Defect 1 — Celery / async-SQLAlchemy loop incompatibility.** `@lru_cache` on `get_async_engine` returned a single AsyncEngine whose asyncpg connections were bound to the loop that opened them. Under Celery — where each task calls `asyncio.run(...)` per invocation — the second task in any worker process inherited connections attached to a closed loop and crashed with `RuntimeError: got Future attached to a different loop`. **Fix:** renamed to `make_async_engine` (no cache); each Celery task constructs + disposes its own engine inside `asyncio.run`'s loop. The FastAPI lifespan owns one process-wide engine via `app.state.db_engine`. Five Celery task sites migrated (`_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once`) plus the lifecycle archive beat task. (Implementation: `1a75c21`.)

2. **Defect 2 — Missing demo fixtures.** `K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx`, `broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, and `broken_malformed_edifact.edi` were referenced by Stage F.3 + F.4 but did not exist. **Fix:** extended `data/_generate.py` with a deterministic openpyxl-based generator producing all four files into `fixtures/`. Determinism was broken in the initial commit (openpyxl re-stamps `dcterms:modified` at save time); the review patch `518232d` rewrites that field in the zip-rewrite pass so re-runs are byte-identical.

3. **Defect 3 — Missing `slack_post` outbox enqueue.** `_validate` wrote only the `audit_log` outbox row, never a `slack_post` row, so the dispatcher had nothing to deliver and Stage F.3.3's "Slack thread reply within 60 s" was structurally impossible. **Fix:** `_validate` now generates the signed URL, builds the Block Kit summary, and enqueues a `slack_post` outbox row inside the same `session.begin()` block as the existing `audit_log` write — preserving the transactional-outbox invariant. The `requested_slack_channel` is recovered from the intake-time `ingress_received` audit_log payload (Phase 5 captured the channel there rather than on `OnrampJob`); the recovery query is read-only and safe because outbox rows are marked `delivered_at` but never deleted.

A fourth regression-guard artifact landed alongside the three fixes: `tests/integration/test_pipeline_e2e.py` (215 LOC, gated by `SOLVO_RUN_E2E_TESTS=1`) — a Celery-driven end-to-end test that would have caught Defect 1 in any Sprint 2 phase review cycle.

---

## §3 — REVIEW PATCH SUMMARY (commit `518232d`)

Step 3B surfaced two patch-worthy items beyond the Codex implementation:

1. **Fixture determinism.** openpyxl's `Workbook.save()` overwrites `wb.properties.modified` to UTC-now during serialization, defeating the pre-save assignment in `_save_demo_workbook`. The patch regex-rewrites `dcterms:modified` inside `docProps/core.xml` during the existing zip-rewrite pass. Verified: two consecutive `python data/_generate.py` runs produce byte-identical SHA256s for all four fixtures (PHASE_6_5_SPEC §8 criterion 7 now satisfied).
2. **Settings env-key acceptance.** The Step 4 `.env` (commit `ace6f48`) added `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` for docker-compose substitution. The `Settings` BaseSettings model under `extra="forbid"` rejected them, breaking unit-test collection for any module that imports `apps.worker.celery_app`. Patched by declaring the three keys as `str = ""` defaults; they remain unused in code (sole purpose is .env compatibility).

---

## §4 — CLOUD RUN DEPLOYMENT URL

Unchanged from the Phase 6 close — Phase 6.5 is code-only; `infra/terraform/`, `cloudbuild.yaml`, and the three Dockerfiles are untouched. The Phase 6 close recorded the deployment URL as deferred to the ops smoke-check on first deploy (see `BUILD_COMPLETE.md` §2 criterion 2). The post-Phase-6.5 Stage F.3 re-run is the gate that produces the live URL in the smoke-test log.

---

## §5 — END-TO-END REGRESSION TEST STATUS

`tests/integration/test_pipeline_e2e.py` is gated behind `SOLVO_RUN_E2E_TESTS=1` and requires a live `docker compose up -d` stack (api + worker + dispatcher + postgres + redis) and a Vertex AI quota allocation (~$0.30 per run). Step 3B did NOT execute this test against the live stack — that execution is the next gate (Step 4 Stage F.3 re-run). Step 3B verified:

- The test file exists and is well-formed.
- The test imports the new symbols (`make_async_engine`, `_recover_requested_slack_channel`, the `slack_post` event type, the Block Kit builder).
- `pytest tests/unit -q` returns 148 passed after the settings patch — no regression in the pre-existing test suite.

The live execution result will be captured in `SMOKE_TEST_LOG.md` during Step 4.

---

## §6 — OUT-OF-SCOPE PRE-EXISTING ITEMS

Documented honestly per the Step 3B pre-existing-failure rule:

- **6 mypy strict errors in `packages/compliance/retention.py`** (Function missing return annotation; `google.cloud.aiplatform` attribute resolution). These were introduced in commit `dfaf079` ("ops: Stage F.2 unblocked — model swap to Gemini 3.1, VERTEX_LOCATION=global, SDK fallback") — well before Phase 6.5. Not addressed in this approval cycle; tracked separately for a follow-up ops cycle.
- **gitleaks scan not re-run this cycle.** The Phase 6.5 diff was inspected manually for secrets (none introduced). The prior Phase 6 approval included a clean gitleaks pass; no `.env`, key file, or credential string lands in the new diff.

---

## §7 — HANDOFF TO HAFEEDH

Phase 6.5 close authorizes a re-run of **Step 4 Stage F.3–F.5** against the now-fixed pipeline:

- **Stage F.3 — Magic Moment × 3.** Submit `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` against the live compose stack via `POST /v1/intake/jobs`. Expected: job reaches `status=completed` within ~90 s (Defect 1 fix); the dispatcher posts a Slack Block Kit summary to the requested channel within ~5 s of validation commit (Defect 3 fix); the `~45 / ~2 / ~3` normalized/flagged/rejected band per PHASE_6_5_SPEC §6.2 holds within tolerance.
- **Stage F.4 — Broken fixtures.** Submit each of `broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi`. Expected: deterministic Stage-4 rejections with `port_unknown_unlocode` / `negative_base_rate` rule citations; the EDIFACT file fails inside the deterministic Stage-1 / Stage-2 path before any LLM call.
- **Stage F.5 — Demo recording.** With F.3 and F.4 green, record the 4–5 minute Vidyard walkthrough per `outreach_bundle.md`.

Step 4 is owned by Hafeedh. Step 3B (this file) stops at the approval handoff; it does not execute the live smoke run.

---

**Sprint 2 closed.**
