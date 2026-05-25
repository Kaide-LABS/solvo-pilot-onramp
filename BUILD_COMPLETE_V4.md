# BUILD COMPLETE — Sprint 2 (post Phase 6.8 closure)

**Status: SPRINT 2 CODE-COMPLETE. F.3-F.5 final re-run authorized.** All 14 defects across three closure phases plus three direct-ops fixes are fixed. Demo recording is gated on the next Step 4 Stage F.3-F.5 pass against the Phase 6.8 stack.

This is the fourth (and final) closure record for Sprint 2. `BUILD_COMPLETE.md` (Phase 6 close), `BUILD_COMPLETE_V2.md` (post Phase 6.5 close), and `BUILD_COMPLETE_V3.md` (post Phase 6.6 close) remain on disk as the historical record. Do not delete them.

---

## §1 — All 14 Defects Fixed

### Phase 6.5 closure (V2 record) — Defects 1, 2, 3

1. **Defect 1** — Celery / async-SQLAlchemy cross-loop. Per-task `make_async_engine` + `finally: engine.dispose()` across all Celery task bodies.
2. **Defect 2** — Missing demo fixtures. `broken_*` fixtures regenerated; determinism patches (dcterms:modified rewrite, sorted zip members, pinned RNG seed) at `518232d`.
3. **Defect 3** — Missing `slack_post` outbox enqueue. `_validate` success-path now enqueues it alongside `audit_log`.

### Phase 6.6 closure (V3 record) — Defects 4, 5, 6, 7

4. **Defect 4** — Missing shared `staging` volume in `docker-compose.yml`. Added named volume mounted at `/tmp/onramp` on api + worker.
5. **Defect 5** — `get_vertex_client` module-level cache. Removed; per-call construction.
6. **Defect 6** — Failure-handler `update_job_status` rolled back by propagating raise. Introduced `_failure_payload` + `_commit_failure` helpers; all three failure paths (`_extract`, `_normalize`, `_validate`) now commit failure-status + audit_log in a fresh `session.begin()` block before re-raising.
7. **Defect 7** — F.3 budget vs fixture-size mismatch. 50-lane K+N fixture shrunk to 15 lanes; F.3.1 budget recalibrated 90s → 180s. Determinism contract preserved.

### Direct-ops fixes (V3 / V4 records) — Defects 8, 9, 10, 11, 12

8. **Defect 8** (commit `ace72d6`) — `fixtures/conformal_calibration_v1.json` not copied into worker image. `Dockerfile.worker` + `.dockerignore` updated.
9. **Defect 9** (commit `ace72d6`) — `storage.Client()` constructed without `project=` in `signed_url.py`. Now reads `get_settings().gcp_project_id`.
10. **Defect 10** (commit `6d3ed3f` + Hafeedh IAM grant) — V4 signed URL needs private-key signer. Local OAuth has only access token. Resolved via (a) `iam.serviceAccountTokenCreator` grant on the signer SA AND (b) explicit `access_token=creds.token` + `credentials=creds` kwargs so the SDK routes through IAMCredentials.signBlob.
11. **Defect 11** (commit `99453a1`) — `get_slack_client` had `@lru_cache(maxsize=1)` keyed on unhashable `Settings`. Per-call construction; mirrors Phase 6.6 §6.2 Vertex client pattern.
12. **Defect 12** (commit `99453a1`) — `get_result_url` route called `async with session.begin():` after an implicit autobegin from a prior read on the same dependency-injected session. Explicit `await session.commit()` inserted between the read and the write begin block; same anti-pattern fixed at `record_intake_review`.

### Phase 6.8 closure (this record) — Defects 13, 14

13. **Defect 13** — `aiohttp` missing in `pyproject.toml` deps. `slack_sdk.AsyncWebClient` requires it at runtime; slack_sdk lists it under `[async]` extras which pip does not auto-install. Added `aiohttp>=3.9.0` directly to top-level deps. (NOT `slack_sdk[async]` — direct add is the more transparent contract.)
14. **Defect 14** — `_validate` never uploaded the normalized JSON to GCS. The result-url endpoint signed `gs://<bucket>/jobs/<job_id>/normalized_ratesheet.json` but nothing wrote that blob. Closed via the transactional outbox: new `upload_result` event type, `_validate` enqueues it alongside `audit_log/validated` + `slack_post` in one atomic transaction, new `deliver_upload_result` handler in `packages/dispatcher/delivery.py` reads `OnrampOutput.normalized_payload` and uploads via the new `packages/storage/upload.py:upload_normalized_json` (mirrors `signed_url.py`'s credential pattern; `Cache-Control: no-cache, max-age=0`; no inner retry — dispatcher owns retries).

### F.3.1 budget re-baseline (Phase 6.8)

F.3.1 acceptance: 180s → **240s**. Aspirational warm-stack target stays 180s. Cold-cache variance in the Vertex Pro ensemble (gRPC channel setup + IAMCredentials.signBlob warm-up on the first ~5 Pro calls of a fresh session) consistently added ~30-35s at the V3/V4/V5 attempts that reached normalize. Tightening the per-lane ensemble timeout was considered and rejected (would raise the EnsembleError rate on legitimate slow Pro calls). `Solvo_Master_PRD.md` §3.3 narrative updated to "about three to four minutes".

### Integration test hardening (Phase 6.8)

`tests/integration/test_pipeline_e2e.py` happy-path now asserts exactly one `upload_result` outbox row, fetches the signed URL via `/v1/intake/jobs/{job_id}/result-url`, GETs the blob with 3 × 2s retries to absorb the dispatcher drain race, and parses the result JSON. Locks Defect 14 against future regression — the smoke run no longer has to manually verify GCS upload, the test does.

---

## §2 — Commit SHAs

### Sprint 2 main build (historical)

- Phase 6 close: `69a757e`
- BUILD_COMPLETE.md: `69a757e`

### Phase 6.5 closure (V2 record, historical)

- Implementation: `1a75c21`
- Review patch: `518232d`
- Approval: `3b35e17`
- BUILD_COMPLETE_V2.md: `e99cfb4`

### Phase 6.6 closure (V3 record, historical)

- Implementation: `55bcb5e`
- Review patch: `4111415`
- Approval: `b50ab72`
- BUILD_COMPLETE_V3.md: `c30b928`

### Direct-ops fixes (Defects 8-12)

- Defects 8 + 9 patch: `ace72d6`
- Defect 10 SDK-shape patch: `6d3ed3f`
- Defects 11 + 12 patch: `99453a1`
- V3 halt record: `ace72d6`
- V4 halt record: `6d3ed3f`
- V5 halt record: `9bb5bd5`

### Phase 6.8 closure (this record)

- Spec: `5adc397` — `docs: Phase 6.8 closure patch spec — third iteration (Defects 13 + 14 + F.3.1 re-baseline)`
- Implementation: `0ef35c7` — `feat: Phase 6.8 implementation (Sprint 2)`
- Review patch: none — code passed review clean on first pass.
- Approval: `83366ae` — `chore: Phase 6.8 review approved (Sprint 2)`
- BUILD_COMPLETE_V4.md: this commit

---

## §3 — Pre-Existing Out-of-Scope Items (Cross-Reference)

Documented in PHASE_6_5_SPEC §9, PHASE_6_6_SPEC §9, and PHASE_6_8_SPEC §9; verified still present and explicitly NOT blocking Sprint 2 closure:

- **6 `mypy --strict` errors in `packages/compliance/retention.py`** from commit `dfaf079` (Stage F.2 Vertex SDK fallback / `google.cloud.aiplatform` shim).
- **1 `mypy --strict` error in `packages/storage/signed_url.py:51`** from commit `6d3ed3f` (Defect 10 patch — `creds.refresh()` is an untyped call from `google-auth`'s type stubs). The new `upload_normalized_json` in `packages/storage/upload.py` carries the matching `# type: ignore[no-untyped-call]` on its corresponding `creds.refresh()` line to avoid contributing a NEW error.

Tracked separately for a post-engagement type-stub sweep.

No other pre-existing failures observed. `pytest tests/unit -q` reports 148 passing. `ruff check .` clean.

---

## §4 — Cloud Run Deployment URL

Unchanged from the Phase 6 close. Phase 6.8 is code-only (one dep + outbox event + dispatcher handler + storage helper + test hardening + spec/PRD prose) — `infra/terraform/`, `cloudbuild.yaml`, and the three Dockerfiles are untouched. The deployment URL records during the post-closure ops smoke pass; see `BUILD_COMPLETE.md` §2 criterion 2, `BUILD_COMPLETE_V2.md` §4, and `BUILD_COMPLETE_V3.md` §4.

---

## §5 — Handoff to Hafeedh

**Sprint 2 code is final.** The gate to demo recording is the Step 4 Stage F.3-F.5 re-run against the Phase 6.8 stack.

### Pre-run action

**Hafeedh must grant** `roles/storage.objectAdmin` (or `roles/storage.objectCreator`) on the outputs bucket to the user OAuth principal that runs the local-compose worker:

```bash
gcloud storage buckets add-iam-policy-binding gs://kaide-solvo-onramp-dev-staging \
  --member="user:sharedkaide.io@gmail.com" \
  --role="roles/storage.objectAdmin"
```

(Bucket name to confirm against `.env` `GCS_BUCKET_OUTPUTS`. The user account is the same one already holding `iam.serviceAccountTokenCreator` from the Defect 10 grant.)

Without this grant, `deliver_upload_result` will fail with `google.api_core.exceptions.Forbidden: 403 ... does not have storage.objects.create access` — that would be a Defect 15, not a Phase 6.8 regression, but would block F.3 sign-off.

### Smoke gate

1. **Stage F.3 — Magic Moment × 3**: drive the 15-lane K+N fixture three times under the recalibrated **240s** F.3.1 budget. Counts 9-13 / 0-3 / 1-3. Outbox `audit_log/validated` + `slack_post` + `upload_result` all delivered. `slack_post.delivered_at` within 5-10s of validation commit. Signed URL fetch returns 200 with valid JSON.
2. **Stage F.4 — Broken-fixture validation**: three broken fixtures → correct rule citations (`port_unknown_unlocode`, `negative_base_rate`, EDIFACT parse failure).
3. **Stage F.5 — Audit-trail verification**: `/internal/v1/audit` returns ordered event sequence; no PII; signed URL TTL honoured.
4. **Vidyard recording (Hafeedh + Isaac)**: post F.3-F.5 pass. Storyboard reflects 15-lane / ~3-4-minute narrative per `Solvo_Master_PRD.md` §3.3.

If F.3-F.5 PASSES: write `SMOKE_TEST_LOG.md` entry + a final ops commit marking the demo recording authorized.

If F.3 surfaces a NEW defect class (Defect 15+) — i.e., one not covered by Defects 1-14 above — halt and write `HUMAN_INTERVENTION_REQUEST_V6.md`. The escalation has slowed (V3 surfaced 3 defects, V4 surfaced 2, V5 surfaced 2 — each iteration finds fewer); Phase 6.8 lands the test that should prevent any further Defect-14-class surface from surviving a smoke run.

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
| Phase 6.6 (closure) | Defects 4-7 (staging volume, Vertex cache, failure handler, fixture shrink + budget) | ✓ Approved |
| Direct ops (V3, V4) | Defects 8-12 (Dockerfile COPY, GCS project, IAM-API signing, Slack lru_cache, result-url tx) | ✓ Landed |
| Phase 6.8 (closure) | Defects 13-14 (aiohttp dep, GCS upload outbox event) + F.3.1 re-baseline + test hardening | ✓ Approved |

**Sprint 2 code complete. F.3-F.5 final re-run authorized. Demo recording un-blocked pending smoke pass.**
