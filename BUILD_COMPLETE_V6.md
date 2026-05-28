# BUILD COMPLETE — V6 (Sprint 2 final closure)

**Status:** Sprint 2 build complete after Phase 7 closure. All 18 defects (1–18, including 18a / 18b / 18c / 18d sub-defects) are closed. Stage F.4–F.5 final re-run authorized; F.3 does NOT need to re-run (V7 results stand).

## Closure cycle: Phase 7 (Defects 18a + 18b + 18c + 18d)

Spec: `PHASE_7_SPEC.md` (commit `18c7799`).
Human intervention request consumed: `HUMAN_INTERVENTION_REQUEST_V8.md` (commit `d05e190`).

### Defects fixed

- **18a — Stage 2 LLM-smuggled rejection records.** `excel_extractor.py` `setdefault`→direct-assignment for `conformal_scores` / `flagged_for_review` / `deterministically_rejected`; `prompts.py` SYSTEM_INSTRUCTIONS gained the shape-violating bullet (`'ZZ@ZZ'`, `'foo'`, `'12345'`) and a strengthened empty-containers clause; `normalizer.py` Stage 3 carve-out passes shape-violating port codes (failing `^[A-Z]{2}[A-Z0-9]{3}$`) through to Stage 4 so R1 emits `port_unknown_unlocode` instead of `port_obfuscation_unresolved`.
- **18b — EDIFACT validity_end ignored DTM+36.** `edifact_extractor.py` new `_parse_dtm_segment` + `_extract_interchange_validity` helpers; full-segment pre-cluster scan captures pre-LIN DTM+36 / DTM+137; parsed dates override Flash-hallucinated validity_start/end on per-cluster basis (cluster DTMs take precedence over interchange-wide).
- **18c — `onramp_audit_log` never written.** `tasks.py` new `_audit_row` helper + inline `session.add(OnrampAuditLog(...))` in `_classify`, `_extract`, `_normalize`, `_validate`, and `_commit_failure`, atomic inside each existing `session.begin()` block. `delivery.py` `deliver_audit_log` docstring updated; remains a no-op (no double-insert). 4-row floor in F.5 now satisfied.
- **18d — Test-architecture blind spot.** New `tests/integration/test_stage_pipeline_mocked.py` with 6 tests (4 spec-mandated + 2 autonomous-critique extras: Stage 3 carve-out + static-source wiring detector). Mock-only — no httpx, no docker-compose; `get_vertex_client` patched at every call site. Plus F.3 happy-path tail assertion at `test_kn_15_lane_reaches_completed_and_emits_slack_post` (purely additive; Defect 6 regression test untouched).

### Commits

| Step | SHA | Message |
|------|-----|---------|
| Phase 7 spec | `18c7799` | docs: Phase 7 closure patch spec — final iteration (Defects 18a + 18b + 18c + test-architecture gate 18d) |
| Phase 7 implementation | `4a1a257` | feat: Phase 7 implementation (Sprint 2) |
| Phase 7 fix patches | — | none (review clean) |
| Phase 7 approval | `00f84dc` | chore: Phase 7 review approved (Sprint 2) |

### Cloud Run deployment URL

Unchanged — Phase 7 is code-only. The previously deployed onramp service URL from the V5 closure record stands until V9 F.4–F.5 re-run.

### Out-of-scope pre-existing test failures (carried forward)

These were documented in `PHASE_6_6_SPEC §9`, `PHASE_6_8_SPEC §10`, `PHASE_6_9_SPEC §10`, and now Phase 7 §9. They do NOT block Sprint 2 closure:

- `packages/compliance/retention.py`: 6 mypy `--strict` errors (from `dfaf079`) — `google.cloud.aiplatform` attr-defined + untyped helper.
- `packages/storage/signed_url.py:51`: 1 mypy error (from `6d3ed3f`) — untyped `Credentials.refresh` call.
- `tests/unit/test_ratesheet_models.py:56/57/60`: 3 mypy dict-item errors.

### Acceptance criteria (Phase 7 §8)

All 15 items confirmed by 3B review:

1. 18a extractor fix verified ✓
2. 18a prompt fix verified ✓
3. 18a Stage 3 carve-out verified (mocked test passes) ✓
4. 18b EDIFACT DTM-override fix verified (mocked test on `broken_malformed_edifact.edi` fixture) ✓
5. 18c inline `OnrampAuditLog` writes in all 4 success paths + `_commit_failure` ✓
6. 18d 6 mocked tests pass under vanilla `pytest tests/integration` ✓
7. F.3 happy-path additive tail assertion only — no other modifications ✓
8. Defect 6 regression test (`test_normalize_failure_surfaces_as_status_failed`) unchanged ✓
9. `pytest tests/unit -q` → 153 passed ✓
10. `pytest tests/integration/test_stage_pipeline_mocked.py -q` → 6 passed ✓
11. `ruff check .` on changed files → clean ✓
12. `ruff format --check` → clean ✓
13. `mypy --strict` on changed files → clean (only pre-existing out-of-scope errors remain) ✓
14. No new secrets in diff ✓
15. V9 F.4–F.5 readiness — gated on V9, not Phase 7 acceptance ✓

### Anti-Replication boundary

Phase 7 is pure infrastructure work — extractor cleanup, prompt amendment, normalizer carve-out, EDIFACT DTM parsing, audit-log table writes, test hardening. No pricing logic, no POMDP / belief state inference, no active learning, no Solvo engine feedback, no statistical confidence intervals on pricing decisions. Boundary preserved.

### Hard invariants preserved

- Pydantic `ConfigDict(extra="forbid")` — no new `BaseModel` subclasses in diff.
- Vertex AI region binding, model strings, zero-retention, boot validators — untouched.
- Deterministic Stage 1 + Stage 4 — new EDIFACT helpers are pure-Python; `apply_hard_rules` untouched.
- N=3 ensemble at (0.1, 0.5, 0.9) and majority-vote consensus — untouched.
- Transactional outbox — row counts unchanged; inline `OnrampAuditLog` writes are additive inside the same `session.begin()` blocks.
- Redis distributed locks, per-task `AsyncEngine`, per-call Vertex client — untouched.
- Phase 6.9 `RejectionRecord.lane_id` REQUIRED + R1..R7 precedence + value-citing `rule_description` — untouched.
- New Phase 7 invariant — rejection rule_ids are sourced solely from `apply_hard_rules`, asserted by `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source`.

## Defect lineage 1–18 with closure SHAs

| Defect | Closure SHA | Phase |
|--------|-------------|-------|
| 1 | `c30b928` | 6.6 closure (BUILD_COMPLETE_V3) |
| 2 | `c30b928` | 6.6 closure |
| 3 | `c30b928` | 6.6 closure |
| 4 | `c30b928` | 6.6 closure |
| 5 | `c30b928` | 6.6 closure |
| 6 | `c30b928` | 6.6 closure |
| 7 | `c30b928` | 6.6 closure |
| 8 | `6d3ed3f`–`99453a1` | 6.7 / 6.8 (intermediate halts) |
| 9 | `6d3ed3f`–`99453a1` | 6.7 / 6.8 |
| 10 | `6d3ed3f` | 6.7 closure (carried to 6.8) |
| 11 | `99453a1` | 6.7 → 6.8 closure |
| 12 | `99453a1` | 6.7 → 6.8 closure |
| 13 | `83366ae` | 6.8 closure (BUILD_COMPLETE_V4) |
| 14 | `83366ae` | 6.8 closure |
| 15 | `abaa97d` | 6.8 closure (F.3.1 re-baseline) |
| 16 | `326da07` | 6.9 closure (BUILD_COMPLETE_V5) |
| 17 | `326da07` | 6.9 closure |
| 18a | `4a1a257` | Phase 7 closure (this record) |
| 18b | `4a1a257` | Phase 7 closure |
| 18c | `4a1a257` | Phase 7 closure |
| 18d | `4a1a257` | Phase 7 closure |

## Handoff to Hafeedh

Step 4 Stage F.4–F.5 final re-run authorized against the post-Phase-7 stack at HEAD `4a1a257` (plus the empty approval commit). F.3 does NOT need to re-run — V7 results stand.

**If F.4 + F.5 PASS, demo recording is authorized for Vidyard with Isaac.** Sprint 2 closure is then FINAL.

If either F.4 or F.5 surfaces a new live-stack defect, halt and write `HUMAN_INTERVENTION_REQUEST_V9.md`; we will re-open with a Phase 8 closure spec.

— Step 3B (review) handoff, 2026-05-27.
