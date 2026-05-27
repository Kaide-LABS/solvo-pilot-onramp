# HUMAN INTERVENTION REQUEST V8 — F.4/F.5 halted on three Defect-18 sub-items

**Step 4 V8 status: HALTED at F.4-F.5.** Sprint 2 Phase 6.9 stack rebuilt and brought up cleanly; F.4 ran all three broken fixtures to terminal status; F.5 audit endpoint queried successfully. Outcomes expose three new defects that each require design judgment and therefore breach the autonomous-patch halt rule of Step 4 V8.

Repo HEAD: `4962cfc` (BUILD_COMPLETE_V5.md). All Phase 6.9 artifacts verified on disk (RejectionRecord.lane_id, value-citing rule_descriptions, mangled port codes ZZ@ZZ/QQ@QQ, DTM+36:20261231). Boot validators pass after `--force-recreate` of api+worker (Docker-on-Windows DNS quirk; pre-existing, recovered automatically on container recreate).

Demo recording remains BLOCKED until Defects 18a, 18b, 18c are closed by a Phase 7 (or equivalent) closure patch.

---

## §0 — Vertex Spend This Run

Three live jobs executed (broken_impossible_port_codes, broken_negative_rates, broken_malformed_edifact). Estimated Vertex cost ~$0.30-$0.60 (Stage 2 Flash-lite single-call + Stage 3 Pro N=3 ensemble per job). Well under the $5 ceiling. Halt reason is design judgment, not budget.

---

## §1 — F.4 Results (literal)

| Fixture | Status | First rule_id | Lane_id | Rule_description | Verdict |
|---|---|---|---|---|---|
| broken_impossible_port_codes.xlsx | completed (79s) | `INVALID_PORT_CODE` | `"4"` | "Origin port code ZZ@ZZ does not match UN/LOCODE format." | ✗ FAIL (Defect 18a) |
| broken_negative_rates.xlsx | completed (96s) | `negative_base_rate` | `"4"` | "base_rate_usd=-2400 is zero or negative; R2 requires a strictly positive USD amount" | ✓ PASS |
| broken_malformed_edifact.edi | completed (19s) | `validity_window_in_the_past` | `"edi-row-1"` | "validity_end=2023-12-31 is before today (2026-05-27 UTC); rate is stale" | ✗ FAIL (Defect 18b) |

Provenance per Phase 6.9: every rejection across all three carries non-null `lane_id` AND non-null value-citing `rule_description` ✓.

---

## §2 — Defect 18a — Stage 2 extractor LLM smuggles rejection records past `setdefault`

**Symptom.** broken_impossible_port_codes.xlsx returns 2 rejections with `rule_id="INVALID_PORT_CODE"` (uppercase, snake_case-ish, LLM-invented) and rule_description `"Origin port code ZZ@ZZ does not match UN/LOCODE format."` (different format than Phase 6.9 `_evaluate_lane` produces — no quotes, no regex citation, "format" instead of "shape").

**Root cause.** `packages/ingest/excel_extractor.py:199` uses `body.setdefault("deterministically_rejected", [])`. `setdefault` only inserts when the key is MISSING. The Stage 2 prompt (`packages/ingest/prompts.py:29`) says `deterministically_rejected MUST be empty in your response — later stages populate them`, but the Gemini-3.1-flash-lite extractor ignores the instruction and emits its own rejection records for shape-violating port codes. Because `setdefault` is permissive, the LLM-smuggled records flow through `NormalizedRatesheet.model_validate(body)` (rule_id is a free-form `str`, not a Literal). Stage 4's `apply_hard_rules` then starts with `list(rs.deterministically_rejected)` and appends only what it sees — but the bad-shape lanes were never put into `lanes` by the LLM, so Stage 4's R1 branch never gets to evaluate them.

This silently violates the §3.5 Stage 4 deterministic-rejection contract ("Stage 4 final validation is pure-Python rules"): in the live stack, rejections originate from Stage 2's LLM, not from Stage 4's regex.

**Why it didn't trip Phase 6.9 review.** The unit tests bypass Stage 2 entirely (they build a `LaneRecord` via `PortCode.model_construct(code="zz")` and feed it directly to `apply_hard_rules`). The integration test was only checked for syntactic validity at 3A/3B per spec §6.4. The live behavior surfaced only at V8.

**Resolution options (need decision).**
- (A) **Force-overwrite at the extractor.** Change `setdefault` → `body["deterministically_rejected"] = []` so Stage 2 can never smuggle rejections. Risk: any lane the LLM chose to reject (rather than `omit` per prompt instruction) gets erased entirely — those rows simply disappear from the pipeline. Acceptable only if we also tighten the prompt to force "always include bad-shape lanes in `lanes`, never reject them in Stage 2."
- (B) **Translate LLM-emitted rule_ids to Phase 6.9 canonical IDs in the extractor.** Map `INVALID_PORT_CODE` → `port_unknown_unlocode`, etc. Brittle and depends on the LLM's chosen vocabulary.
- (C) **Accept the LLM-side rejection as the canonical path for shape violations.** Update Phase 6.9 acceptance criteria to allow `INVALID_PORT_CODE` as an equivalent rule_id. Documents the de-facto behavior but means Stage 4's R1 branches are dead code in the live stack.

Recommendation: **(A) plus prompt tightening.** Restores the Stage 4 deterministic-rejection invariant. Smallest surface-area change.

---

## §3 — Defect 18b — EDIFACT extractor ignores fixture DTM+36, infers `validity_end=2023-12-31`

**Symptom.** broken_malformed_edifact.edi returns 1 rejection with `rule_id="validity_window_in_the_past"`, `rule_description="validity_end=2023-12-31 is before today (2026-05-27 UTC); rate is stale"`. R3 still masks the structural-malformation defect the fixture was designed to surface.

**Root cause hypothesis (needs investigation).** The fixture contains:
```
UNB+...+260501:1200+1++PRICAT'UNH+1+PRICAT:D:01B:UN:EAN999'BGM+9+ORDER123+9'
DTM+137:20260501:102'DTM+36:20261231:102'NAD+SU+SUPPLIER123++Sample Supplier'
LIN+1++PRODUCT001:SA'PIA+5+12345:SA'IMD+F++:::SampleItem'QTY+1:100'
PRI+AAA:1000:CT'UNS+S'CNT+2:1'UNT+11+1'UNZ+1+1'
```

`DTM+36:20261231:102` is the spec-mandated future end-of-validity. But `validity_end=2023-12-31` came out the other side — which means `packages/ingest/edifact_extractor.py` either (i) doesn't parse `DTM+36`, (ii) hits the UNT segment-count mismatch error and falls back to a hardcoded default, or (iii) uses a different segment for validity_end entirely. Need to inspect the extractor source.

**Resolution.** Either fix the EDIFACT extractor to parse DTM+36 (or whichever qualifier it actually uses), or change Phase 6.9 §6.1.4 to future-date whichever segment the extractor actually reads. Either path touches Stage 2 logic (excluded from autonomous-patch authority).

**Cross-check.** Phase 6.9 §6.1.4 anticipated exactly this case: "If the file does NOT contain a DTM+36 segment, then the validity_end came from a default elsewhere in the extractor — the agent reports the actual source and Phase 6.9 §6.1.4 reframes to extraction-fallback default future-dated." The spec gave us escape hatch language but Codex did not run the diagnostic. We need to run it now.

---

## §4 — Defect 18c — `onramp_audit_log` table never written; F.5 returns 0 entries

**Symptom.** F.5 audit endpoint returns `[]` for the broken_impossible_port_codes job. Direct SQL: `SELECT count(*) FROM onramp_audit_log;` → 0 across all jobs ever run.

**Root cause.** Pipeline tasks (`packages/ingest/tasks.py`) enqueue audit-trail entries via `enqueue_outbox_event(event_type="audit_log", payload=...)`. This writes one row to `onramp_outbox` only. The dispatcher's audit_log delivery handler at `packages/dispatcher/delivery.py:121`:

```python
async def deliver_audit_log(payload: dict[str, Any], _settings: Settings) -> dict[str, Any]:
    """audit_log delivery is a no-op — the row already lives in onramp_audit_log."""
    _log.debug("audit_log delivered (no-op): %s", payload.get("stage"))
```

…asserts the row "already lives in onramp_audit_log" — but `grep -rn "OnrampAuditLog(" packages/ apps/` finds **zero** call sites that actually insert into the table (only the route reads it, the dispatcher no-ops it, and `lifecycle/archive.py` only references it for retention). The table is created by migration `0003_audit_trail` but no code path writes to it.

The current outbox state confirms the gap:

```
 event_type   | delivered | count
---------------+-----------+-------
 audit_log    | true      |    18
 slack_post   | true      |     3
 upload_result| true      |     3
 access_log   | true      |     1
```

18 audit_log events delivered to `/dev/null` by the dispatcher. F.5 will never pass.

**Resolution options (need decision).**
- (A) Make the success-path tx in `_classify/_extract/_normalize/_validate` write to `OnrampAuditLog` directly in the same `session.begin()` block as the outbox enqueue. Matches transactional-outbox semantics; removes the dispatcher no-op.
- (B) Make `deliver_audit_log` perform the insert. Easier patch but introduces a new transactional surface (dispatcher → audit table) that doesn't currently exist.

Recommendation: **(A)**. Mirrors how `OnrampOutput`, `onramp_jobs.status`, `onramp_conformal_scores` are written today (inline in the same `session.begin()` block as the outbox enqueue) and aligns with the §3.4 invariant that audit_log writes commit atomically with the work they document.

Schema note: V8 spec assumed audit_log columns `actor_type` and `actor_id`; the actual schema (from `0003_audit_trail`) has `actor` (text) and `actor_principal` (text). Phase 7 closure should reconcile the V8 check column names against the schema OR rename the columns to match V8 expectations. Recommend renaming the V8 check (less risk).

---

## §5 — F.5 Sub-Checks That DID Pass

- **F.5.1 admin-auth gate:** no-auth → 403 ✓; bearer-token with fake job_id → 404 ✓. The route signature and token check are correct.
- **F.5.3 PII scan:** zero violations on the (empty) audit response. Trivially passes but is meaningless until Defect 18c is closed.
- **F.5.4 field completeness:** trivially passes on an empty list. Meaningless until 18c.

So once Defect 18c is closed, F.5 will likely pass on the first run — F.5.1 already works, and the audit_log payloads emitted into the outbox today are field-rich (we can see them in `onramp_outbox.payload`).

---

## §6 — Commit SHAs & Artifacts From This V8 Attempt

- Stack rebuilt + brought up clean: api+worker required `--force-recreate` because of the Windows-Docker DNS staleness on first cold-start (cosmetic; not a real defect).
- F.4 jobs: `be2c79fb808341fbb2b3330611b9f57e` (bpc), `18e3bfe5ab99448dbcf49c454d8f8400` (bnr), `0b09f1c5e3634045903a8d044c53e7f0` (bme).
- Result blobs cached at `C:/Users/hp/AppData/Local/Temp/bpc.json`, `.../bnr.json`, `.../bme.json`.
- Audit endpoint dump: `C:/Users/hp/AppData/Local/Temp/audit.json` (empty list, as expected).
- No code commits this run. Local-only diagnostic file `_v8_test_broken.sh` written and gitignored (or simply uncommitted).

No code commits — this halt is diagnostic only.

---

## §7 — Handoff

**Demo recording remains BLOCKED** until Defects 18a, 18b, 18c are closed. Phase 7 closure scope:

1. **18a** — extractor force-overwrite + Stage 2 prompt tightening so all lanes (including bad-shape) flow into `lanes` for Stage 4.
2. **18b** — diagnose EDIFACT validity_end provenance via the extractor source; either patch the extractor to parse DTM+36 (or the qualifier it actually uses) or future-date the right segment in `fixtures/broken_malformed_edifact.edi`.
3. **18c** — write `OnrampAuditLog` rows in the success-path tx alongside outbox enqueues; dispatcher's `deliver_audit_log` no-op stays; reconcile actor field names (`actor`+`actor_principal` vs V8's expected `actor_type`+`actor_id`).

Strongly recommend a single Phase 7 closure spec covering all three. Phase 6.9 closed Defects 16/17 cleanly at the schema + rules-engine level; Defects 18a-c are the live-stack manifestations the unit tests couldn't surface.

Out-of-scope items from prior closures (still tracked): retention.py 6 mypy errors, signed_url.py 1 mypy error, test_ratesheet_models.py 3 dict-item errors.

When Phase 7 lands and a V9 re-run of F.4-F.5 passes against the patched stack, Vidyard recording with Isaac is authorized.
