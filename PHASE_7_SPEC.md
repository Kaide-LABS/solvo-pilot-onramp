# PHASE 7 SPEC — Live-Stack Closure Patch (Final)

**Output of Step 2 (Phase 7 spec generation).** Consumes the Step 4 Stage F.4-F.5 halt at commit `d05e190` (`HUMAN_INTERVENTION_REQUEST_V8.md`) and the BUILD_COMPLETE_V5 closure record at `4962cfc`. Feeds a single Step 3A build cycle, a single Step 3B review cycle, then a V9 Stage F.4-F.5 resume (F.3 does NOT need to re-run; V7 results stand). After Phase 7 lands and V9 F.4-F.5 passes, Sprint 2 closure is FINAL and demo recording is authorized.

---

## §0 — Phase Plan Header

**This is Phase 7 of the Sprint 2 build — the final closure patch following the Step 4 Stage F.4-F.5 halt at commit `d05e190` (HUMAN_INTERVENTION_REQUEST_V8.md). Phase 6.5 closed Defects 1-3. Phase 6.6 closed Defects 4-7. Direct ops commits closed Defects 8-12. Phase 6.8 closed Defects 13-14. Channel-rename ops closed Defect 15. Phase 6.9 closed Defects 16-17 at the schema and rules-engine level. Phase 7 closes Defects 18a + 18b + 18c — the three live-stack defects that Phase 6.9's unit tests structurally could not catch. Phase 7 also adds a new acceptance gate (a Stage 2→3→4 pipeline-integration test with deterministic Vertex mocks) that closes the structural blind spot. After Phase 7 lands and V9 F.4-F.5 passes, Sprint 2 closure is FINAL.**

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 – 6 | Sprint 2 build | Scaffolding through Cloud Run deployment. |
| ✅ Phase 6.5 | post-F.3 halt #1 | Defects 1-3. |
| ✅ Phase 6.6 | post-F.3 halt #2 | Defects 4-7. |
| ✅ Direct ops (V3+V4) | post-V3+V4 halts | Defects 8-12. |
| ✅ Phase 6.8 | post-F.3 halt #3 (V5) | Defects 13-14 + F.3.1 budget re-baseline. |
| ✅ Channel rename | post-F.3 halt #4 (V6) | Defect 15. |
| ✅ Phase 6.9 | post-F.4 halt (V7) | Defects 16-17 (schema + rules-engine + fixtures). |
| **Phase 7** | post-F.4-F.5 halt (V8) | **Defects 18a + 18b + 18c + 18d (test-architecture gate).** |

**Scope:**

- **Defect 18a — Stage 2 LLM-smuggled rejection records.** `packages/ingest/excel_extractor.py:199` uses `body.setdefault("deterministically_rejected", [])` which is permissive; the LLM (gemini-3.1-flash-lite) emits its own `INVALID_PORT_CODE` rejections that flow through, bypassing Stage 4 R1. V8 evidence: `broken_impossible_port_codes.xlsx` returned `rule_id="INVALID_PORT_CODE"` with `rule_description="Origin port code ZZ@ZZ does not match UN/LOCODE format."` — invented by the LLM, not from the Phase 6.9 deterministic R1 branch. Resolution: force-overwrite the field at the extractor + tighten the Stage 2 prompt to require bad-shape lanes flow into `lanes` rather than being rejected at Stage 2. Per V8 halt doc recommendation (A).
- **Defect 18b — EDIFACT extractor returns past `validity_end` despite future `DTM+36` segment.** V8 evidence: fixture has `DTM+36:20261231:102`, extractor returned `validity_end=2023-12-31`. Root cause must be diagnosed in `packages/ingest/edifact_extractor.py` before scoping the fix. Resolution depends on diagnosis: (i) if DTM+36 isn't parsed, patch the extractor to parse it; (ii) if UNT mismatch triggers a fallback default, fix the fallback to honor parsed DTM segments first; (iii) if a different segment is used for validity_end, future-date that segment in `fixtures/broken_malformed_edifact.edi` instead.
- **Defect 18c — `onramp_audit_log` table never written.** `enqueue_outbox_event(audit_log, ...)` writes to the outbox; the dispatcher's `deliver_audit_log` no-ops claiming "the row already lives in onramp_audit_log"; no code path inserts into `onramp_audit_log`. V8 evidence: 18 audit_log events delivered, `SELECT count(*) FROM onramp_audit_log` returns 0; F.5 audit endpoint returns `[]`. Resolution: make the success-path transactions in `_classify/_extract/_normalize/_validate` write `OnrampAuditLog` rows directly inline with the outbox enqueues, atomically with the work they document. Per V8 halt doc recommendation (A).
- **Defect 18d — Test-architecture blind spot.** Phase 6.9's integration tests checked syntactic validity at 3A/3B but never ran the full Stage 2→3→4 pipeline against broken fixtures. The unit tests bypassed Stage 2 entirely via `PortCode.model_construct(code="zz")`. Resolution: add a new `tests/integration/test_stage_pipeline_mocked.py` that runs the full pipeline against each broken fixture with a deterministic Vertex mock fixture, asserting that rejection records originate from `apply_hard_rules` (not from Stage 2's LLM smuggle path) and that DTM+36 segments are honored by the EDIFACT extractor. This test runs in the standard `pytest tests/integration -q` invocation during 3A/3B WITHOUT requiring live Vertex.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 7.** Per ULTIMATE_PRD §4.7, provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 7 introduces no new academic claims — it is pure live-stack fix work plus test-architecture hardening.

---

## §1 — Files Added or Modified

**Modified:**

- `packages/ingest/excel_extractor.py` — **MODIFIED**. Around lines 197-199, change `body.setdefault(...)` to direct-assignment for `conformal_scores`, `flagged_for_review`, and `deterministically_rejected` (defense-in-depth — same smuggle vector applies to all three). Three line-edits, no new imports, no signature change. The `NormalizedRatesheet.model_validate(body)` call on the next line accepts the empty containers cleanly.
- `packages/ingest/prompts.py` — **MODIFIED**. The Stage 2 SYSTEM_INSTRUCTIONS string gets two amendments:
  - Add a new bullet: *"Lanes with shape-violating port codes (e.g. 'ZZ@ZZ', 'foo', '12345') MUST be included in `lanes` with the port code passed through unchanged. Do NOT reject them at extraction. Do NOT omit them. Stage 4 validation will reject them with deterministic rule citations."*
  - Strengthen the existing `deterministically_rejected MUST be empty` clause to read: *"`deterministically_rejected`, `flagged_for_review`, and `conformal_scores` MUST be empty arrays/dicts in your response. Any content you place there will be erased before downstream processing."*
- `packages/ingest/edifact_extractor.py` — **MODIFIED (diagnostic-driven).** The 3A build agent reads the file via Nia/github.sh and diagnoses the actual source of `validity_end=2023-12-31` for `fixtures/broken_malformed_edifact.edi`. Three likely paths (per §6.2):
  - (i) **DTM+36 not parsed.** Patch the extractor to parse `DTM+36:<date>:102` (CCYYMMDD format per UN/EDIFACT D.96A qualifier 36 = end-of-validity).
  - (ii) **UNT count-mismatch triggers a fallback default.** Fix the fallback to honor parsed DTM segments first, OR fail-loud rather than synthesizing a past date.
  - (iii) **A different segment is the actual validity source.** Document which segment in §6.2 and future-date that segment in the fixture instead.
  The Phase 7 spec does NOT pre-commit which path applies — the 3A agent picks based on what the diagnostic finds and reports it in the handoff.
- `packages/ingest/normalizer.py` — **MODIFIED**. Around lines 257-272: when `origin.canonical is None or destination.canonical is None`, instead of unconditionally flagging the lane for `port_obfuscation_unresolved`, check whether the failure is shape-based (the input code doesn't match `^[A-Z]{2}[A-Z0-9]{3}$`) and pass the lane through to Stage 4 in that case. Stage 4's R1 then fires with the canonical `port_unknown_unlocode` rule_id. This is the Stage-3 carve-out for the 18a fix — without it, shape-violating port codes get flagged at Stage 3 before R1 ever sees them.
- `packages/ingest/tasks.py` — **MODIFIED**. Four functions: `_classify`, `_extract`, `_normalize`, `_validate`. Each currently calls `enqueue_outbox_event(event_type="audit_log", payload=...)` inside a `session.begin()` block. Add an inline `session.add(OnrampAuditLog(...))` call in the same transaction, populating the `actor`, `actor_principal`, `action`, `payload` columns from the same data that feeds the outbox payload. Atomic with the work being documented. Phase 6.6 §6.3 failure-path carve-out preserved: failure-path audit_log writes commit in their own fresh `session.begin()` block via `_failure_payload` / `_commit_failure`. Those helpers also get the inline `OnrampAuditLog` write.
- `packages/dispatcher/delivery.py` lines 121-123 — **MODIFIED (docstring only)**. The `deliver_audit_log` no-op behavior stays (no double-insert). Docstring updated to: *"audit_log delivery is a no-op — the row was inserted inline in the originating transaction (Phase 7 §6.3)."*
- `tests/integration/test_pipeline_e2e.py` — **MODIFIED**. Three changes:
  - `test_broken_impossible_port_codes_rejects_with_port_unknown_unlocode` (Phase 6.9): assertion expectations confirmed against post-18a behavior — first rejection's `rule_id` should now match the Phase 6.9 canonical `port_unknown_unlocode`. No assertion text change expected; the spec was already written against the canonical.
  - `test_broken_negative_rates_rejects_with_negative_base_rate` (Phase 6.9): already passes per V8 evidence; no change.
  - `test_broken_malformed_edifact_rejects_with_structural_citation` (Phase 6.9): assertion adapts to whichever 18b path the 3A agent picks. If extractor parses DTM+36 successfully, the test asserts no `validity_window_in_the_past` rejection AND any rejection cites a structural rule. If extractor fails parse, `status="failed"` is acceptable.
  - `test_kn_15_lane_reaches_completed_and_emits_slack_post` (F.3 happy-path): gains ONE additive tail assertion — query `OnrampAuditLog` for the test job_id, assert `count >= 4`, assert all rows have non-null `actor` and `actor_principal`. THIS is the only spec-permitted modification to the F.3 happy-path test. Narrow, additive, locks Defect 18c against future regression.

**Added:**

- `tests/integration/test_stage_pipeline_mocked.py` — **NEW**. Phase 7's structural-blind-spot fix (Defect 18d). Runs the full Stage 2→3→4 pipeline against the three broken fixtures with deterministic Vertex mocks. Tests:
  - `test_full_pipeline_broken_impossible_port_codes` — asserts rejection rule_id is the Phase 6.9 canonical `port_unknown_unlocode`, NOT an LLM-emitted `INVALID_PORT_CODE` (18a regression detector).
  - `test_full_pipeline_broken_malformed_edifact` — reads `fixtures/broken_malformed_edifact.edi`, runs the EDIFACT extractor directly (no Vertex needed for this path), asserts `validity_end >= date(2026, 6, 1)` (18b regression detector).
  - `test_full_pipeline_writes_audit_log` — runs the full pipeline against a broken fixture, queries `SELECT count(*) FROM onramp_audit_log WHERE job_id = <job>`, asserts `>= 4` (18c regression detector).
  - `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source` — under the Vertex mock, asserts `apply_hard_rules` is called exactly once per job and zero LLM calls occur between Stage 4 start and rejection emission. Stage 4 deterministic invariant lock.

  The Vertex mock is a `pytest` fixture that returns hardcoded deterministic responses for the broken fixtures. The mock short-circuits at the `get_vertex_client` boundary — no Vertex calls, no quota burn. Runs in vanilla `pytest tests/integration -q`.

- `tests/conftest.py` — **MODIFIED (conditionally)**. If the deterministic Vertex mock requires a session-scoped fixture, register it here. If it's test-local, this file isn't touched.

**Deleted:** none. All prior closure records, halt records, and spec files remain on disk.

---

## §2 — Pip Dependencies

**None expected.** Phase 7 is logic + tests. The Vertex mock uses `unittest.mock` (stdlib) and/or `pytest-mock` (verify against `pyproject.toml` `[dev-dependencies]`). If a new test dep is genuinely needed, add it to `[dev-dependencies]` and document.

---

## §3 — Pydantic Schemas

**No schema changes.** `RejectionRecord` retains the Phase 6.9 shape (source_row_reference, lane_id, rule_id, rule_description). `OnrampAuditLog` ORM class is untouched — Phase 7 just starts writing to it.

---

## §4 — FastAPI Route Signatures

**No route changes.** The audit-read endpoint at `apps/api/routes/audit.py` is unmodified; it just starts returning non-empty arrays after 18c is closed.

---

## §5 — Alembic Migration

**No new migration.** `migrations/versions/0003_audit_trail.py` already creates `onramp_audit_log` with the right columns (`audit_id`, `job_id`, `actor`, `action`, `payload`, `actor_principal`, `occurred_at`, `request_id`). Phase 7 writes to existing columns.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 18a Fix (Stage 2 LLM Smuggle)

#### §6.1.1 — Extractor force-overwrite

In `packages/ingest/excel_extractor.py` around lines 197-199:

```python
# BEFORE (permissive — LLM can smuggle)
body.setdefault("conformal_scores", {})
body.setdefault("flagged_for_review", [])
body.setdefault("deterministically_rejected", [])

# AFTER (force-overwrite — Stage 2 cannot smuggle)
body["conformal_scores"] = {}
body["flagged_for_review"] = []
body["deterministically_rejected"] = []
```

Three line-edits. No new imports. No signature changes. `NormalizedRatesheet.model_validate(body)` on the next line accepts the empty containers cleanly.

#### §6.1.2 — Stage 2 prompt tightening

In `packages/ingest/prompts.py` SYSTEM_INSTRUCTIONS:

- Add new bullet: *"Lanes with shape-violating port codes (e.g. 'ZZ@ZZ', 'foo', '12345') MUST be included in `lanes` with the port code passed through unchanged. Do NOT reject them at extraction. Do NOT omit them. Stage 4 validation will reject them with deterministic rule citations."*
- Strengthen existing clause to: *"`deterministically_rejected`, `flagged_for_review`, and `conformal_scores` MUST be empty arrays/dicts in your response. Any content you place there will be erased before downstream processing."*

#### §6.1.3 — Stage 3 normalizer carve-out

Without this, shape-violating port codes flow into `lanes` (per the prompt tightening) but get flagged for `port_obfuscation_unresolved` at `packages/ingest/normalizer.py` ~line 268 because `resolve_port_code` returns `canonical=None`. R1 never fires. Patch the carve-out: when both/either canonical is None AND the input code fails the `^[A-Z]{2}[A-Z0-9]{3}$` regex, pass the lane through to Stage 4 unchanged rather than flagging. Stage 4's R1 then fires with the canonical `port_unknown_unlocode` rule_id.

Pseudocode:

```python
_SHAPE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")

origin = await resolve_port_code(resolved_lane.origin_port.code, session)
destination = await resolve_port_code(resolved_lane.destination_port.code, session)
if origin.canonical is None or destination.canonical is None:
    origin_shape_bad = not _SHAPE.match(resolved_lane.origin_port.code)
    dest_shape_bad = not _SHAPE.match(resolved_lane.destination_port.code)
    if origin_shape_bad or dest_shape_bad:
        # Shape-violating: pass through; Stage 4 R1 will reject deterministically.
        final_lanes.append(resolved_lane)
        continue
    # Otherwise shape-valid but table-unknown — flag for review as before.
    flags.append(FlaggedLane(lane=resolved_lane, reason="port_obfuscation_unresolved", confidence=None))
    continue
```

The 3A agent reads the actual line numbers and adapts.

### §6.2 — Defect 18b Fix (EDIFACT Validity)

**Diagnostic step first.** Read `packages/ingest/edifact_extractor.py` fully. Find where `validity_end` is assigned. Three likely paths:

- **Path A**: A regex/parser reads `DTM+\d+:(\d{8}):102` and extracts dates by qualifier. If qualifier 36 isn't in the matched qualifier set, patch the regex/parser to include 36.
- **Path B**: The parser hits an exception on the UNT count mismatch and falls back to a hardcoded `datetime(2023, 12, 31)` (or equivalent past-default). Patch the fallback to honor any successfully-parsed DTM+36 segment before applying its default, OR change the fallback from a past-default to a fail-loud raise (so the integration test sees `status="failed"`).
- **Path C**: The parser reads `DTM+137` (qualifier 137 = document/message date/time) and uses that as validity_end. The fix is to read DTM+36 instead, OR to update the fixture to future-date DTM+137 (in addition to or instead of DTM+36).

The 3A agent picks the path based on the actual code shape and reports the choice in the handoff. The spec does NOT pre-commit because the underlying behavior is opaque from the file inventory alone.

**Test coverage:** the new `test_stage_pipeline_mocked.py` includes a test that reads `fixtures/broken_malformed_edifact.edi`, runs the EDIFACT extractor directly (no Vertex needed), and asserts `validity_end >= date(2026, 6, 1)`. This locks 18b against future regression regardless of which diagnostic path the 3A agent took.

### §6.3 — Defect 18c Fix (Audit-Log Table Writes)

For each of `_classify`, `_extract`, `_normalize`, `_validate` in `packages/ingest/tasks.py`, the success-path `session.begin()` block currently looks like:

```python
async with factory() as session, session.begin():
    # ... task-specific writes (OnrampOutput upsert, status update) ...
    await enqueue_outbox_event(
        session,
        job_id=job_id,
        event_type="audit_log",
        payload={"stage": "<stage_name>_completed", ...},
    )
```

Patch each block to add an inline `session.add(OnrampAuditLog(...))` immediately after the outbox enqueue:

```python
async with factory() as session, session.begin():
    # ... task-specific writes ...
    audit_payload = {"stage": "<stage_name>_completed", ...}
    await enqueue_outbox_event(
        session,
        job_id=job_id,
        event_type="audit_log",
        payload=audit_payload,
    )
    session.add(
        OnrampAuditLog(
            job_id=job_id,
            actor="worker",
            actor_principal="pipeline-task",
            action="<stage_name>_completed",
            payload=audit_payload,
        )
    )
```

The exact column values come from `migrations/versions/0003_audit_trail.py`: `actor` (text), `actor_principal` (text), `action` (text), `payload` (jsonb). `occurred_at` defaults to `now()`. `request_id` stays null in worker-task contexts. The 3A agent verifies column names against the migration before writing the code.

**Failure-path carve-out** (Phase 6.6 §6.3): `_failure_payload` / `_commit_failure` helpers also write an inline `OnrampAuditLog` row inside their fresh `session.begin()` block. Mirror the pattern with `action="<stage_name>_failed"`, `actor="worker"`, `actor_principal="pipeline-task"`. Failure-path audit row commits atomically with the failure-status outbox enqueue.

**Dispatcher no-op:** `deliver_audit_log` stays a no-op (no double-insert). Docstring updated per §1.

**V8 column-name reconciliation:** the V8 halt doc raised a schema-vs-V8 column mismatch concern (`actor_type`/`actor_id` vs actual `actor`/`actor_principal`). Phase 7 keeps the actual schema unchanged (the migration is locked); the V9 smoke script (and any test code referencing `actor_type`/`actor_id`) must rename to `actor`/`actor_principal`. The 3A agent grep-locates such references and corrects them. Do NOT touch the migration.

### §6.4 — Defect 18d Fix (Test-Architecture Gate)

Create `tests/integration/test_stage_pipeline_mocked.py`:

```python
"""Phase 7 §6.4 — Full Stage 2→3→4 pipeline integration test with Vertex mocked.

Closes the structural blind spot that let Defects 18a/18b escape Phase 6.9
review: unit tests bypassed Stage 2 via PortCode.model_construct; integration
tests only checked syntactic validity. This test runs the full pipeline against
broken fixtures with a deterministic Vertex mock, then asserts rejection
records originate from apply_hard_rules (not from Stage 2's LLM smuggle path).

Runs in: pytest tests/integration -q
Live Vertex required: NO
"""
```

Four tests (sketch — 3A agent fills in implementation against the actual task functions):

- `test_full_pipeline_broken_impossible_port_codes(deterministic_vertex_mock, db_session)`:
  Run `_extract → _normalize → _validate` against `fixtures/broken_impossible_port_codes.xlsx` with the Vertex mock returning bad-shape lanes in `lanes`. Assert `OnrampOutput.normalized_payload.deterministically_rejected` contains a record with `rule_id == "port_unknown_unlocode"` AND no record has `rule_id == "INVALID_PORT_CODE"` (18a regression detector). Assert every rejection has non-null `lane_id` and value-citing `rule_description` (Phase 6.9 invariant lock).

- `test_full_pipeline_broken_malformed_edifact(db_session)`:
  Read `fixtures/broken_malformed_edifact.edi` and call the EDIFACT extractor directly (no Vertex needed). Assert the resulting LaneRecord has `validity_end >= date(2026, 6, 1)` (18b regression detector). If the extractor raises by design, the test instead asserts the exception type and message clarity.

- `test_full_pipeline_writes_audit_log(deterministic_vertex_mock, db_session)`:
  Run the full pipeline on a broken fixture. Query `SELECT count(*) FROM onramp_audit_log WHERE job_id = :job_id`. Assert `>= 4` (one row per stage). Assert all rows have non-null `actor` and `actor_principal` (18c regression detector).

- `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source(deterministic_vertex_mock, db_session)`:
  Patch `apply_hard_rules` to count calls. Patch `get_vertex_client` to count LLM invocations. Run the full pipeline on a broken fixture. Assert `apply_hard_rules` is called exactly once for the job AND zero Vertex calls occur between the `apply_hard_rules` entry and the rejection emission. Stage 4 deterministic invariant lock.

The **Vertex mock** (`deterministic_vertex_mock` pytest fixture) short-circuits at the `get_vertex_client` boundary. For each broken fixture, it returns a hardcoded `NormalizedRatesheet` body where:
- bad-shape port codes are LEFT IN the `lanes` array (per the 18a fix expectation),
- negative rates are LEFT IN the `lanes` array,
- `deterministically_rejected` / `flagged_for_review` / `conformal_scores` are all empty.

Pydantic-mock fidelity matters: the mocked payload must be exactly what a real Stage 2 LLM would emit POST-18a fix. The 3B reviewer audits this fidelity by reading both the mock and the prompt to verify they describe the same contract.

---

## §7 — Cross-Phase Integration Requirements

Phase 7 must NOT break:

- **Phase 6.5 per-task `make_async_engine`.** Untouched.
- **Phase 6.6 per-call `get_vertex_client`.** Untouched.
- **Phase 6.6 `_failure_payload` / `_commit_failure`.** Extended with inline `OnrampAuditLog` writes per §6.3, but failure-path semantics (fresh session, separate transaction, propagate raise) preserved.
- **Phase 6.8 success-path transactional outbox.** Currently 4 outbox rows (audit_log + slack_post + upload_result + the status/output writes). After Phase 7, the success-path tx writes one additional row: the `OnrampAuditLog` row alongside the outbox enqueues. Strictly additive — outbox row count unchanged.
- **Phase 6.9 `RejectionRecord.lane_id` REQUIRED field and value-citing `rule_description`.** Untouched.
- **Stage 4 R1..R7 precedence and `apply_hard_rules` public signature.** Untouched.
- **F.3 happy-path test.** The new audit-row tail assertion is strictly additive — existing assertions unchanged.
- **Defect 6 regression test.** Untouched.
- **§3.10 retention posture**, including the 365-day floor on audit_log.
- **Anti-Replication boundary.** No pricing, no POMDP, no RL, no market-clearing.

---

## §8 — Phase 7 Acceptance Criteria

3A build + 3B review approve when ALL true:

1. **18a extractor fix verified:** `packages/ingest/excel_extractor.py` uses direct-assignment (`body["..."] = []`) for the three keys, not `setdefault`. Static inspection.
2. **18a prompt fix verified:** `packages/ingest/prompts.py` SYSTEM_INSTRUCTIONS contains the new shape-violating bullet AND the strengthened empty-containers clause. Static inspection.
3. **18a Stage 3 carve-out verified:** `packages/ingest/normalizer.py` lets shape-violating port codes pass through to Stage 4. Verified by `test_full_pipeline_broken_impossible_port_codes`.
4. **18b fix verified:** `packages/ingest/edifact_extractor.py` produces `validity_end >= date(2026, 6, 1)` for the broken fixture. Diagnostic path (A/B/C) documented in the 3A handoff. Verified by `test_full_pipeline_broken_malformed_edifact`.
5. **18c fix verified:** All 4 task success paths (`_classify`, `_extract`, `_normalize`, `_validate`) and all 2 failure-path helpers (`_failure_payload`, `_commit_failure`) write `OnrampAuditLog` rows inline. Verified by `test_full_pipeline_writes_audit_log`.
6. **18d fix verified:** `tests/integration/test_stage_pipeline_mocked.py` exists, contains the four test functions outlined in §6.4, runs in `pytest tests/integration -q` without live Vertex. All four pass.
7. **F.3 happy-path test minimal addition:** `test_kn_15_lane_reaches_completed_and_emits_slack_post` gains a tail assertion on `OnrampAuditLog` row count `>= 4` and non-null `actor`+`actor_principal`. No other modifications. Verify via `git diff` showing additions only.
8. **Defect 6 regression test unchanged.** Verify via `git diff`.
9. **`pytest tests/unit -q` passes baseline (148 prior + 5 Phase 6.9 net-new = 153).** No regressions.
10. **`pytest tests/integration -q` passes the new mocked-pipeline tests** (Phase 7 §6.4). F.3/F.4 live-Vertex integration tests do NOT run during 3A/3B; they run during V9.
11. **`ruff check .` clean.**
12. **`ruff format --check .` clean.**
13. **`mypy --strict` clean on changed files.** Pre-existing retention.py/signed_url.py/test_ratesheet_models.py errors remain out-of-scope per their original carve-outs.
14. **No new secrets in the diff.**
15. **V9 F.4-F.5 readiness.** Phase 7 acceptance does NOT require running V9; that's the next Step 4 attempt against the Phase 7 stack.

---

## §9 — Explicit NON-GOALS for Phase 7

- **No new rules added to `apply_hard_rules`.** R1..R7 set is locked.
- **No `BUILD_COMPLETE_V6.md` written by Phase 7 itself.** That lands after V9 F.4-F.5 actually passes.
- **No retention.py / signed_url.py / test_ratesheet_models.py mypy cleanup.**
- **No K+N fixture regeneration.**
- **No Master PRD or ULTIMATE_PRD prose changes.**
- **No `PHASE_8_SPEC.md`. Sprint 2 ends at Phase 7 close + V9 F.4-F.5 pass.**
- **No new outbox event types.**
- **No deletion of prior closure records, halt records, or spec files.**
- **No backfill of `onramp_audit_log` for historical jobs.** Forward-only.
- **No re-running of F.3.** V7 results stand.
- **No changes to `RejectionRecord` schema.** Phase 6.9 shape is locked.
- **No changes to the dispatcher's `deliver_audit_log` other than the docstring update.**
- **No schema changes to `OnrampAuditLog`** or its migration.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_6_9_SPEC.md`.
- Do NOT modify any `BUILD_COMPLETE*.md` file.
- Do NOT modify any `HUMAN_INTERVENTION_REQUEST*.md` file.
- Do NOT modify `Solvo_Master_PRD.md` or `ULTIMATE_PRD.md`.
- Do NOT modify the F.3 happy-path test except for the additive audit-row tail assertion.
- Do NOT modify the Defect 6 regression test.
- Do NOT touch R1..R7 precedence or `apply_hard_rules` public signature.
- Do NOT add a new rule.
- Do NOT introduce a new env var.
- Do NOT change `OnrampAuditLog` schema or its migration.
- Do NOT modify the K+N happy-path fixture.
- Do NOT change the transactional outbox row counts beyond adding the inline `OnrampAuditLog` write — strictly additive.

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`.
- All Vertex AI calls bind to `location='global'` with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation.
- Container-boot validators fail-fast on misconfiguration.
- Anti-Replication boundary: no pricing, POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing, no rate / margin / recommendation computation.
- **Transactional outbox**: success-path 3 outbox rows + `OnrampOutput` upsert + status='completed' update + **NEW**: `OnrampAuditLog` row, all in one transaction. Failure-path commits its own fresh transaction with failure-status + audit_log/{stage}_failed outbox row + **NEW**: failure-path `OnrampAuditLog` row.
- Redis distributed locks use `SET NX EX`.
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus.
- Per-task `make_async_engine` (Phase 6.5) preserved.
- Per-call `get_vertex_client` (Phase 6.6) preserved.
- Deterministic Stage 1 + Stage 4 — zero LLM calls in `classify_format` or in `apply_hard_rules` or any of its R1..R7 branches.
- **NEW Phase 7 invariant**: Rejection records emitted into `OnrampOutput.normalized_payload.deterministically_rejected` MUST have `rule_id` in the Phase 6.9 canonical literal set: `port_unknown_unlocode`, `negative_base_rate`, `validity_window_in_the_past`, `validity_window_inverted`, `transit_time_out_of_range`, `equipment_type_unknown`, `surcharge_basis_unknown`. LLM-emitted free-form rule_ids (e.g. `INVALID_PORT_CODE`) are forbidden and are a Phase 7 regression detector.

— End of PHASE_7_SPEC.md.
