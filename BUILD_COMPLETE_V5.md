# BUILD COMPLETE — Sprint 2 (post Phase 6.9 closure)

**Status: SPRINT 2 CODE-COMPLETE. F.4-F.5 final re-run authorized. F.3 does NOT need to re-run (V7 results stand).** All 17 defects across four closure phases plus three direct-ops fixes are fixed. Demo recording is gated on the next Step 4 Stage F.4-F.5 pass against the Phase 6.9 stack.

This is the fifth (and final) closure record for Sprint 2. `BUILD_COMPLETE.md`, `BUILD_COMPLETE_V2.md`, `BUILD_COMPLETE_V3.md`, `BUILD_COMPLETE_V4.md` remain on disk as the historical record. Do not delete them.

---

## §1 — Defects 16 + 17 Closed (Phase 6.9)

### Defect 16 — F.4 broken-fixture validity masks named defects

The deterministic rules engine evaluates R1..R7 in fixed order; R3 (`validity_window_in_the_past`) fired before R1/R2 on every broken fixture because all three carried past validity windows. The named defect each fixture was designed to surface never got attributed.

**Resolution:** fixture refresh, NOT rule re-ordering. Phase 4's R1..R7 precedence preserved verbatim.

- `fixtures/broken_impossible_port_codes.xlsx` — Codex added `validity_start` / `validity_end` columns with future dates (2026-06-01 / 2026-12-31). Review patch (`9af8c33`) mangled the port codes `ZZZZZ` → `ZZ@ZZ` (row 4 origin) and `QQQQQ` → `QQ@QQ` (row 6 destination) so they fail the `^[A-Z]{2}[A-Z0-9]{3}$` regex deterministically. Without the mangle, the codes passed the regex and R1 would not have fired in the live stack (spec §6.1.2 was explicit on this).
- `fixtures/broken_negative_rates.xlsx` — validity columns future-dated; -2400 base_rate_usd preserved.
- `fixtures/broken_malformed_edifact.edi` — `DTM+36:20261231:102` end-of-validity segment added after the existing `DTM+137`. UNT segment-count mismatch (declared 11, actual higher) preserved as the named structural defect.

### Defect 17 — RejectionRecord provenance gap

- **17a — missing `lane_id`.** `RejectionRecord` carried `source_row_reference` (sheet/row/cell) but not the originating `LaneRecord.lane_id`. Master PRD §3.3 promises "deterministically rejected with rule-ID provenance"; operators reading the Slack summary need lane-level traceability. Fix: `lane_id: str = Field(min_length=1, max_length=64)` added to `RejectionRecord` as REQUIRED (no default, no Optional). `apply_hard_rules` emits `RejectionRecord(..., lane_id=lane.lane_id, ...)`.
- **17b — static `rule_description`.** Was a label from `_RULE_DESCRIPTIONS` ("origin or destination port code does not match UN/LOCODE shape"). Now value-citing per branch: each R1..R7 path composes the description from the lane's actual fields (e.g. `"origin port code 'ZZ@ZZ' does not match the UN/LOCODE shape ^[A-Z]{2}[A-Z0-9]{3}$"`). `_RULE_DESCRIPTIONS` dict retained as the rule-category catalogue for audit-log grouping.
- R1 split into two arms (origin-fail, destination-fail) so the value-citing text correctly identifies which side failed.
- `_evaluate_lane` signature unchanged. `apply_hard_rules` public signature unchanged. Zero LLM calls (Stage 4 deterministic invariant preserved).

**Autonomous critique acknowledged:** V7's halt doc framed Defect 17 as "null `rejection_reason` / null `lane_id`" — but the schema had `rule_description`+`source_row_reference` (both populated), no `rejection_reason` field. The "null" observation was a smoke-script key-mismatch artifact. The V8 smoke script must update its key references from `rejection_reason` to `rule_description`.

### Tests

- `tests/unit/test_rules_engine.py` — 11 tests: golden + R1 origin/destination + R2..R7 + first_violation_wins + lane_id_provenance. 153 unit tests total passing (148 prior + 5 net new).
- `tests/integration/test_pipeline_e2e.py` — 3 new F.4 broken-fixture tests + 3 private helpers (`_submit_broken_fixture`, `_fetch_signed_blob`, `_assert_rejection_provenance`). F.3 happy-path (`test_kn_15_lane_reaches_completed_and_emits_slack_post`) and Defect 6 regression (`test_normalize_failure_surfaces_as_status_failed`) UNMODIFIED.
- `tests/unit/test_ratesheet_models.py` minimal-valid-payload includes `"lane_id": "L1"` on `RejectionRecord` (otherwise the parametrized strict-forbid test fails).

---

## §2 — Commit SHAs

### Phase 6.9 closure (this record)

- Spec: `6637bb7` — `docs: Phase 6.9 closure patch spec — fourth and final iteration (Defects 16 + 17)`
- V7 halt record: `7424ae5`
- Implementation: `33d0942` — `feat: Phase 6.9 implementation (Sprint 2)`
- Review fix patch: `9af8c33` — `fix: Phase 6.9 review patches (Sprint 2) — mangle xlsx port codes to bad-shape`
- Approval: `326da07` — `chore: Phase 6.9 review approved (Sprint 2)`
- BUILD_COMPLETE_V5.md: this commit

### Prior closure (historical, unchanged)

- Phase 6 close + BUILD_COMPLETE.md: `69a757e`
- Phase 6.5: impl `1a75c21`, review `518232d`, approval `3b35e17`, BUILD_COMPLETE_V2.md `e99cfb4`
- Phase 6.6: impl `55bcb5e`, review `4111415`, approval `b50ab72`, BUILD_COMPLETE_V3.md `c30b928`
- Direct-ops Defects 8+9 patch: `ace72d6`
- Direct-ops Defect 10 SDK-shape patch: `6d3ed3f`
- Direct-ops Defects 11+12 patch: `99453a1`
- Phase 6.8: spec `5adc397`, impl `0ef35c7`, approval `83366ae`, BUILD_COMPLETE_V4.md `abaa97d`
- Channel-rename ops (Defect 15): `265c0e9`

---

## §3 — Complete Defect Lineage (1–17)

### Phase 6.5 (V2 record)
1. **Defect 1** — Celery / async-SQLAlchemy cross-loop. Per-task `make_async_engine` + `finally: engine.dispose()`. Closure SHA: `3b35e17`.
2. **Defect 2** — Missing demo fixtures regenerated with determinism patches. Closure SHA: `518232d`.
3. **Defect 3** — Missing `slack_post` outbox enqueue in `_validate` success path. Closure SHA: `3b35e17`.

### Phase 6.6 (V3 record)
4. **Defect 4** — Missing shared `staging` volume in docker-compose. Closure SHA: `b50ab72`.
5. **Defect 5** — `get_vertex_client` module-level cache removed. Closure SHA: `b50ab72`.
6. **Defect 6** — Failure-handler `update_job_status` rollback fixed via `_failure_payload` + `_commit_failure`. Closure SHA: `b50ab72`.
7. **Defect 7** — F.3 budget vs fixture size: 50→15 lanes, 90s→180s. Closure SHA: `b50ab72`.

### Direct-ops (V3/V4 records)
8. **Defect 8** — `conformal_calibration_v1.json` missing from worker image. Closure SHA: `ace72d6`.
9. **Defect 9** — `storage.Client()` missing `project=`. Closure SHA: `ace72d6`.
10. **Defect 10** — V4 signed-URL signer credential path (local OAuth + IAMCredentials.signBlob). Closure SHA: `6d3ed3f` (+ IAM grant).
11. **Defect 11** — `get_slack_client` `@lru_cache` over unhashable `Settings`. Closure SHA: `99453a1`.
12. **Defect 12** — `get_result_url` `async with session.begin()` after autobegin. Closure SHA: `99453a1`.

### Phase 6.8 (V4 record)
13. **Defect 13** — `aiohttp` missing from `pyproject.toml`. Closure SHA: `83366ae`.
14. **Defect 14** — `_validate` never uploaded normalized JSON to GCS (new `upload_result` outbox event + dispatcher handler + `upload_normalized_json`). Closure SHA: `83366ae`.

### Channel rename ops (V4 → V7 bridge)
15. **Defect 15** — Slack channel `#pilot-onramp` → `#solvo-onramp-demo`. Closure SHA: `265c0e9`.

### Phase 6.9 (this V5 record)
16. **Defect 16** — F.4 broken-fixture validity windows mask named defects. Closure SHAs: `33d0942` (impl) + `9af8c33` (review patch on `broken_impossible_port_codes.xlsx` port codes).
17. **Defect 17** — `RejectionRecord` provenance gap (17a `lane_id` + 17b value-citing `rule_description`). Closure SHA: `326da07` (approval over `33d0942`).

---

## §4 — Cloud Run Deployment URL

Unchanged from prior closure records. Phase 6.9 is code-only (3 fixture changes, 1 schema field, rules-engine value-citing strings, tests). `infra/terraform/`, `cloudbuild.yaml`, and the three Dockerfiles are untouched.

---

## §5 — Pre-Existing Out-of-Scope Items (Cross-Reference)

Documented in PHASE_6_5_SPEC §9, PHASE_6_6_SPEC §9, PHASE_6_8_SPEC §9, PHASE_6_9_SPEC §9; verified still present and explicitly NOT blocking Sprint 2 closure:

- **6 `mypy --strict` errors in `packages/compliance/retention.py`** from commit `dfaf079`.
- **1 `mypy --strict` error in `packages/storage/signed_url.py:51`** from commit `6d3ed3f`.
- **3 dict-item typing errors in `tests/unit/test_ratesheet_models.py`** lines 56/57/60 (pre-existing per Phase 6.9 commit-message disclosure).

Tracked separately for a post-engagement type-stub sweep.

---

## §6 — Handoff to Hafeedh

**Sprint 2 code is final. All 17 defects fixed.**

> **Step 4 Stage F.4-F.5 final re-run authorized; F.3 does NOT need to re-run (V7 results stand). If F.4 + F.5 PASS, demo recording authorized for Vidyard with Isaac.**

### Pre-run notes

- V8 smoke script must update its rejection-record key reference from `rejection_reason` → `rule_description` (per Phase 6.9 autonomous critique #1).
- `broken_impossible_port_codes.xlsx` port codes `ZZ@ZZ` / `QQ@QQ` are now bad-shape; R1 will surface `port_unknown_unlocode` on those two rows. Other rows (DEHAM→USNYC, NLRTM→SGSIN, USLAX→JPYOK) are valid-shape and either pass or trigger downstream rules.
- IAM grants from prior closure (Defect 10 `iam.serviceAccountTokenCreator`, BUILD_COMPLETE_V4 §5 `storage.objectAdmin`) remain in place; no new IAM action required.
- Slack channel target is `#solvo-onramp-demo` (Defect 15 rename).
- Cloud Run deployment URL unchanged; redeploy is required to ship the Phase 6.9 fixture binaries + rules-engine + schema patch (`cloudbuild submit` against current `main`).

### Acceptance gates for demo go/no-go

- F.4 — `test_broken_impossible_port_codes_rejects_with_port_unknown_unlocode`, `test_broken_negative_rates_rejects_with_negative_base_rate`, `test_broken_malformed_edifact_rejects_with_structural_citation` all pass against the deployed stack.
- F.5 — full E2E happy + broken combined run (per Step 4 §F.5 acceptance).

If both pass → Vidyard recording with Isaac authorized.
