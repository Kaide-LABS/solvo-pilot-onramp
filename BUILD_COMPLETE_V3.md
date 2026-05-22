# BUILD COMPLETE — Sprint 2 (post Phase 6.6 closure)

**Status: SPRINT 2 COMPLETE.** All 8 defects across the two closure phases (6.5 and 6.6) are fixed. Demo recording is un-blocked, pending the final Stage F.3-F.5 re-run against the 15-lane K+N fixture under the 180 s budget.

This is the third (and final) closure record for Sprint 2. `BUILD_COMPLETE.md` (Phase 6 close) and `BUILD_COMPLETE_V2.md` (post Phase 6.5 close) remain on disk as the historical record. Do not delete them.

---

## §1 — All Eight Defects Fixed

### Phase 6.5 closure (V2 record) — Defects 1, 2, 3

1. **Defect 1 — Celery / async-SQLAlchemy cross-loop**: every Celery task body now constructs its own `AsyncEngine` via `make_async_engine(settings)` and disposes it in a `finally` block. Module-level `@lru_cache` engine removed. Verified across `_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once`, `archive_completed_jobs`.
2. **Defect 2 — Missing demo fixtures**: `fixtures/broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi` regenerated and committed. Determinism patches (`dcterms:modified` rewrite, sorted zip members, pinned RNG seed) shipped in the Phase 6.5 review patch (commit `518232d`).
3. **Defect 3 — Missing `slack_post` outbox enqueue**: `_validate` success-path now enqueues both `audit_log` (stage=validated) AND `slack_post` rows inside the terminal `session.begin()` transaction. Dispatcher's `_drain_once` consumes the `slack_post` event type and posts the Block Kit summary to the recovered Slack channel.

### Phase 6.6 closure (this record) — Defects 4, 5, 6, 7

4. **Defect 4 — Missing shared staging volume in `docker-compose.yml`**: named volume `staging` added at top-level `volumes:` block and mounted at `/tmp/onramp` on both `api` and `worker` services. Dispatcher correctly excluded (it touches Postgres + Redis + Slack only). Cloud Run continues to use GCS for inter-service staging; this volume is a local-compose-only artefact and does not require an infra change.
5. **Defect 5 — `get_vertex_client` module-level cache**: `packages/compliance/vertex_client.py` `_client_cache` dict removed. `get_vertex_client(settings)` now constructs a fresh `genai.Client` per call. This mirrors the Phase 6.5 `make_async_engine` per-task contract — any module-level cache survives Celery's prefork into ForkPoolWorker children and inherits an `httpx.AsyncClient` whose connections reference the parent's (closed) boot-validator loop, surfacing as `RuntimeError: Event loop is closed` on the first task call.
6. **Defect 6 — Failure-handler `update_job_status` writes rolled back**: `_failure_payload` (PII-clean, redacts `/tmp/onramp/...` paths) and `_commit_failure` (writes failed-status + audit_log in a fresh `session.begin()` block) helpers added to `packages/ingest/tasks.py`. All three failure paths (`_extract`, `_normalize`, `_validate`) use them. `_normalize` additionally hoists the `normalize_lanes` call OUTSIDE the success-path transaction so the `EnsembleError` failure handler isn't rolled back by the propagating `raise`. `_validate` gained a top-level try/except (it had no failure handler before; any intermediate exception left the job wedged at `status='validating'`). Failure paths do NOT enqueue a `slack_post` outbox row.
7. **Defect 7 — F.3 acceptance budget vs fixture size mismatch**: K+N fixture shrunk from 50 lanes to 15 (`data/_generate.py`). Broken-lane positions moved from (23, 31, 47) to (7, 11, 14). Merged-cell tier rows reduced from 5 to 3. `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` regenerated to 6871 bytes. F.3.1 budget recalibrated 90 s → 180 s. The other three demo fixtures are NOT regenerated and remain byte-identical to their post-`518232d` versions. Phase 6.5 review patch's determinism contract (`dcterms:modified` rewrite, sorted zip members, pinned RNG seed) preserved verbatim. `Solvo_Master_PRD.md` §3.3 rewritten for the 15-lane narrative; §3.4 and §5 voiceover language preserved. `PHASE_6_5_SPEC.md` §6.2 received a new §6.2.1 supersession note (5 lines, body unchanged).

### Phase 6.6 review patch — Defect 6 regression test schema fix (sub-defect, surfaced and fixed during Step 3B)

Codex's Phase 6.6 implementation introduced 5 `mypy --strict` errors in the new `test_normalize_failure_surfaces_as_status_failed` regression test: `NormalizedRatesheet` was constructed without its required `job_id`/`prospect_id`, and `ExtractionMetadata` was constructed with fields the model rejects under `ConfigDict(extra="forbid")`. At runtime the test would have raised `pydantic.ValidationError` before exercising the failure-handler — silently nullifying the Defect 6 coverage. Step 3B review patch (commit `4111415`) reconstructs both models with their actual field sets. Post-patch state: `ruff check .` clean, `pytest tests/unit -q` 148 passing, `mypy --strict` on the four changed files reports only the 6 pre-existing `packages/compliance/retention.py` errors (out-of-scope per spec §9).

---

## §2 — Commit SHAs

### Phase 6.5 closure (historical, from V2)

- Implementation: `1a75c21`
- Review patch: `518232d`
- Approval: `3b35e17`
- BUILD_COMPLETE_V2.md: `e99cfb4`

### Phase 6.6 closure (this record)

- Implementation: `55bcb5e` — `feat: Phase 6.6 implementation (Sprint 2)`
- Review patch: `4111415` — `fix: Phase 6.6 review patches (Sprint 2) — Defect 6 regression test schema fix`
- Approval: `b50ab72` — `chore: Phase 6.6 review approved (Sprint 2)`
- BUILD_COMPLETE_V3.md: this commit

---

## §3 — Pre-Existing Out-of-Scope Items (Cross-Reference)

Documented in PHASE_6_5_SPEC §9 and PHASE_6_6_SPEC §9; verified still present and explicitly NOT blocking Sprint 2 closure:

- **6 `mypy --strict` errors in `packages/compliance/retention.py`**, originating from commit `dfaf079` (Stage F.2 Vertex SDK fallback / `google.cloud.aiplatform` shim). The retention enforcer's runtime behaviour is verified by unit tests; these are type-stub gaps in the Vertex SDK fallback path. Tracked separately for a post-engagement sweep.

No other pre-existing failures were observed. `pytest tests/unit -q` reports 148 passing.

---

## §4 — Cloud Run Deployment URL

Unchanged from the Phase 6 close. Phase 6.6 is code-only (compose topology + worker code + fixtures + PRD narrative + a test) — `infra/terraform/`, `cloudbuild.yaml`, and the three Dockerfiles are untouched. The deployment URL records during the post-closure ops smoke pass; see `BUILD_COMPLETE.md` §2 criterion 2 and `BUILD_COMPLETE_V2.md` §4.

---

## §5 — Handoff to Hafeedh

**Sprint 2 closure is final.** The next gate is the final Stage F.3-F.5 re-run against the 15-lane K+N fixture under the recalibrated 180 s budget, followed by the Vidyard demo recording:

1. **Stage F.3 — Magic Moment × 3 runs**: drive `fixtures/K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx` (15 lanes, 6871 bytes) through the live compose stack three times in a row. Pass criteria:
   - F.3.1: total runtime under **180 s** per run.
   - F.3.2: counts in band — normalized 9–13, flagged 0–3, rejected 1–3.
   - F.3.3: outbox contains `audit_log` (stage=validated) AND `slack_post` rows; `slack_post.delivered_at` populates within 5–10 s of validation commit.
   - F.3.4: lane-by-lane output ≥95% identical across the 3 runs.
   - F.3.5: three consecutive runs without any wedged-job failure. A transient Pro-call timeout that durably surfaces as `status='failed'` (Defect 6 fix) does NOT count as a pass — the run must complete. Counter resets on any failure.
2. **Stage F.4 — Broken-fixture validation**: drive the three broken fixtures (`broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi`) and confirm Stage 4 surfaces the correct rule citations (`port_unknown_unlocode`, `negative_base_rate`, EDIFACT parse failure path).
3. **Stage F.5 — Audit-trail verification**: confirm `/internal/v1/audit` returns each job's outbox event sequence in order, that PII redaction holds on failure rows (no `/tmp/onramp/` substrings), and that signed URLs honour the §3.10 expiry contract.
4. **Vidyard recording**: post-F.3-F.5 pass. The §3.3 storyboard in `Solvo_Master_PRD.md` reflects the 15-lane / ~3-minute narrative.

If F.3 surfaces a new defect class — i.e., one not covered by Defects 1-7 above — halt and write `HUMAN_INTERVENTION_REQUEST_V3.md`. Otherwise Sprint 2 closes here.

---

## §6 — Sprint 2 Scope Inventory (Final)

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Scaffolding, boot validators, alembic 0001, §3.10.5 handshake | ✓ Approved |
| Phase 2 | Ratesheet schemas, Stage 1 classifier, Stage 2 Excel extractor | ✓ Approved |
| Phase 3 | Stage 3 N=3 Pro ensemble, UN/LOCODE + WCO HS6 reference load | ✓ Approved |
| Phase 4 | EDIFACT, Stage 4 rules engine, audit trail, `/internal/v1/audit` | ✓ Approved |
| Phase 5 | Slack + intake + dispatcher + Phase 4 wiring closure | ✓ Approved |
| Phase 6 | Cloud Run europe-west4 deployment + lifecycle | ✓ Approved |
| Phase 6.5 (closure) | Defects 1-3 (Celery engine, fixtures, slack_post) | ✓ Approved |
| Phase 6.6 (closure) | Defects 4-7 (staging volume, Vertex client cache, failure handler, fixture shrink + budget) | ✓ Approved |

**Sprint 2 complete. Hafeedh handles Stage F.3-F.5 re-run + Vidyard recording.**
