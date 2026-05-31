# HUMAN_INTERVENTION_REQUEST_V11 — Step 4 V11 HALT at Stage F.5 (Defect 22)

**Run:** Step 4 V11 (Phase 9 post-closure smoke). Repo HEAD `45a024a`. Stack rebuilt clean on Phase 9 code.
**Date:** 2026-05-31.
**Verdict:** **Stage F.4 PASSED. Stage F.5 BLOCKED by Defect 22.** Demo recording NOT authorized.
**Halt authority:** DEFECT 22+ HALT RULE — the defect requires design judgment on a Pydantic **schema** (and touches a hard `extra="forbid"` invariant + the Phase 7 §6.3 audit contract). Patch direction is genuinely ambiguous and contradicts one of two authoritative sources. Not a mechanical fix.

---

## Stage F.4 — broken_impossible_port_codes — ✅ PASS (Defect 21 closed LIVE)

The V10 failure mode is closed. With Flash returning only clean lanes (V10's exact behaviour), the deterministic pre-LLM scan still produced both shape-violators.

- **Job:** `7c042249a37b40379301a45b9e7b6116` — `status=completed` in **42s**.
- **`prompt_version=stage2.excel.v2`**, **`cell_count=36`** (true workbook size, captured before the pre-LLM trim).
- **2 `port_unknown_unlocode` rejections** with real Excel provenance:
  - `A4` — `lane_id=shape_violator_Rates_4` — "origin port code 'ZZ@ZZ' does not match the UN/LOCODE shape ^[A-Z]{2}[A-Z0-9]{3}$"
  - `B6` — `lane_id=shape_violator_Rates_6` — "destination port code 'QQ@QQ' does not match the UN/LOCODE shape ^[A-Z]{2}[A-Z0-9]{3}$"
- The `shape_violator_Rates_<row>` lane-IDs confirm the **deterministic pre-LLM path** fired (not Flash). **B6-not-A6 anchor verified live** (the destination-violator cites `B6`, with `raw_origin_code="DEHAM"` recovered separately).
- Full 5-row accounting (no anomaly):
  - rows 2,3 (`DEHAM→USNYC`, `NLRTM→SGSIN`) → `lanes` (clean, resolved)
  - rows 4,6 (`ZZ@ZZ`, `QQ@QQ`) → `deterministically_rejected` (Defect 21 fix)
  - row 5 (`USLAX→JPYOK`) → `flagged_for_review` / `port_obfuscation_unresolved` — the **Phase 7 §6.1.3 normalizer carve-out** (shape-valid but unresolved against the loaded UN/LOCODE subset). Untouched by Phase 9; identical to V9/V10 behaviour. Not a regression.
- No `INVALID_PORT_CODE`; all rule_ids canonical; Phase 6.9 provenance complete.

**Pre-flight all green:** real fixture headers are literally `origin`/`destination` (exact label-set match), sheet `Rates`; in-image Phase 9 code present (`_scan_cells_for_shape_violators`, `stage2.excel.v2`); `/v1/health` `healthy` with all 4 validators (incl. both Vertex handshakes) True.

---

## Stage F.5 — audit trail — ❌ BLOCKED (Defect 22)

### What passed
- No-auth `GET /internal/v1/audit/<fake>` → **403** ✅ (expected 401/403).
- Admin-token `GET /internal/v1/audit/<fake-uuid>` → **404** ✅ (expected 200/404).
- The audit **data is correct and complete** — 4 rows for the BPC job, queried directly from `onramp_audit_log`:

  | action | actor | actor_principal | payload | occurred_at |
  |--------|-------|-----------------|---------|-------------|
  | classified | worker | pipeline-task | ✓ | ✓ |
  | extracted | worker | pipeline-task | ✓ | ✓ |
  | normalized | worker | pipeline-task | ✓ | ✓ |
  | validated | worker | pipeline-task | ✓ | ✓ |

  ≥4 entries ✅, actor constants `worker`/`pipeline-task` ✅, all 6 required fields present ✅, no PII in the row values ✅. **By data, F.5's content criteria are satisfied.**

### What blocks
`GET /internal/v1/audit/7c042249a37b40379301a45b9e7b6116` (the correct bare-hex key) → **HTTP 422**, body:

```
{"error":"validation_error","detail":[
  {"type":"literal_error","loc":["actor"],
   "msg":"Input should be 'system', 'operator' or 'external_webhook'","input":"worker"},
  {"type":"literal_error","loc":["action"],
   "msg":"Input should be 'ingress_received','classify_complete','extract_complete',
          'normalize_complete','validate_complete',...","input":"classified"}, ...]}
```

This is a **response-model serialization failure**, not a data or auth problem. The audit read endpoint can never return a real pipeline job's rows over HTTP.

### Root cause — cross-phase schema drift (Phase 4 ↔ Phase 7 §6.3)

| Component | Writes / Expects | Source |
|-----------|------------------|--------|
| `packages/ingest/tasks.py:_audit_row` (writer) | `actor="worker"`, `actor_principal="pipeline-task"`, `action ∈ {classified, extracted, normalized, validated}` | Phase 7 §6.3 (Defect 18c) |
| `apps/api/routes/audit.py` (`response_model=list[AuditLogEntry]`) | rejects anything not matching the model below | Phase 4 §4.1 |
| `packages/core/models/audit.py:AuditLogEntry` | `actor: Literal["system","operator","external_webhook"]`, `action: AuditAction = Literal["ingress_received","classify_complete","extract_complete","normalize_complete","validate_complete", ...]` | Phase 4 §3.1 |

Phase 7 introduced inline worker audit writes with a new vocabulary but never reconciled the Phase 4 `AuditLogEntry` Literals. The DB column is free `Text`, so writes succeeded silently; the read path only breaks at response serialization — first exercised now, because **F.5 was never reached in any prior smoke run** (V7/V9 halted earlier; the log records "F.4, F.5 — NOT ATTEMPTED").

**Not a Phase 9 defect:** `audit.py`, `audit.py` model, and `tasks.py` are all absent from the Phase 9 diff (`bab8f04..ce3adcb`).

### Why this needs human judgment (not an in-flight patch)

The two authoritative sources **contradict each other**, so no patch is mechanically "obvious":

- **Option A — make the reader match the writer.** Extend `AuditLogEntry.actor` to include `"worker"` and add `classified|extracted|normalized|validated` to `AuditAction`. **Satisfies this task's F.5 assertions** (`actor=="worker"`). But it relaxes/duplicates the Phase 4 §3.1 audit vocabulary (now two action namings co-exist: `classified` vs `classify_complete`), and edits a `extra="forbid"` schema that other code (`AuditRoute`, access-log path, Phase 4 tests) depends on.
- **Option B — make the writer match the reader.** Change Phase 7 §6.3 `_audit_row` to emit canonical `action="classify_complete"`/etc. and `actor="system"`. Keeps the Phase 4 schema pristine. **But it directly contradicts THIS task's F.5 pass criteria**, which assert `actor=="worker"` and `actor_principal=="pipeline-task"`. It also leaves historical rows non-conformant (forward-only).
- **Option C — relax the endpoint.** Drop/loosen `response_model` on the audit route (return raw dicts or a permissive model). Smallest blast radius but weakens the Phase 4 API contract and the audit type-safety guarantee.

Choosing among A/B/C is a schema/contract decision with downstream test and compliance implications — exactly the "design judgment (schema, route signature, invariant touch)" the halt rule reserves for you.

### Recommendation

**Option A**, scoped tightly: the task author's F.5 spec treats `actor="worker"` / `actor_principal="pipeline-task"` as the *intended* stored values, which makes the Phase 4 `AuditLogEntry` Literals the stale artifact. The lowest-risk reconciliation is to widen the reader model to the vocabulary the pipeline actually emits (add `"worker"` to `actor`; add the four short action forms to `AuditAction`), update the Phase 4 audit-model unit tests accordingly, and re-run F.5 only. This keeps the writer (and historical rows) valid and makes the endpoint return what F.5 expects. If instead you consider the Phase 4 long-form vocabulary canonical, take Option B and amend the V11 F.5 spec's actor/action assertions to match.

This is a follow-up patch (call it **Phase 9.1 / Defect 22**), not a re-run of F.4 — F.4 stands.

---

## Spend & state

- **Vertex AI this run:** one Stage-2 Flash extraction (36-cell workbook) + a small Stage-3 Pro normalization pass for ~3 lanes. Estimate **< $1**, well under the $5 ceiling.
- **Stack:** left running and healthy for re-test after the fix. DB has the BPC job + its 4 audit rows.
- **No demo-authorization commit written.** F.4+F.5 did not both pass.

## Handoff

1. Decide Option A / B / C for Defect 22.
2. Apply the patch (reader model or writer or route), update the matching unit tests, run `pytest tests/unit -q`.
3. Re-run **only F.5** against BPC job `7c042249a37b40379301a45b9e7b6116` (still in the DB) — no new Vertex spend needed for F.5. F.4 stands; do not re-run it.
4. If F.5 passes → append to SMOKE_TEST_LOG.md and authorize demo recording.

**Standing results:** F.4 ✅ (V11), BNR ✅ + BME ✅ (V9), F.3 ✅ (V7). Only F.5 outstanding.

— Step 4 V11 halt, 2026-05-31.
