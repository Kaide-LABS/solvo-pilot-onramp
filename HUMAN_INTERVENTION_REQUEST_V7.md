# HUMAN INTERVENTION REQUEST — V7

**Halt at Step 4 Stage F.4.** F.1, F.2, F.3 PASSED. F.4 surfaces two new defects (16 + 17) that both require design judgment — halt per the V7 protocol rule "A defect requires design judgment (Pydantic schema, route signature, or invariant touch)."

Date: 2026-05-26.
Repo HEAD: `265c0e9` (channel-rename commit on top of Phase 6.8 closure).

---

## What did pass

### Channel rename — PASSED at `265c0e9`
8 lines updated across `Solvo_Master_PRD.md`, `ULTIMATE_PRD.md`, `tests/unit/test_intake_models.py`, `tests/unit/test_intake_routes.py`. Unit tests stay at 148 passing; ruff clean. The four GitHub-repo references (README.md, positioning_final.md, prd_patches.md, Solvo_Master_PRD.md line 655) correctly left untouched.

### Stage F.1 — PASSED
Compose stack came up clean after `down -v` + rebuild. Alembic head reached at 0004_intake_review. UN/LOCODE 110000 rows + WCO HS6 5000 rows loaded.

### Stage F.2 — PASSED (4/4 validators)
- `vertex_ai_handshake` → True
- `postgres_alembic_head` → True
- `un_locode_table_integrity` → True
- `vertex_ai_compliance_handshake` → True

### Stage F.3 — PASSED on all three runs against `#solvo-onramp-demo`

| Run | Job ID | Latency | normalized | flagged | rejected | Outbox |
|---|---|---|---|---|---|---|
| 1 | `b68015bcb8584eaca2ad09cc6aff5235` | 178s | 12 | 0 | 1 | 7/7 delivered (audit×5, slack_post, upload_result) |
| 2 | `c626e97018854e489121f35af51516d7` | 168s | 12 | 0 | 1 | 7/7 delivered |
| 3 | `755ee14b82b14e5f948f816ce22be521` | 155s | 12 | 0 | 1 | 7/7 delivered |

- **F.3.1** (≤240s): PASS — max 178s, all three well inside the Phase 6.8 §6.4.3.1 re-baselined ceiling.
- **F.3.2** (counts in 9-13 / 0-3 / 1-3): PASS — 12 / 0 / 1 on every run.
- **F.3.3** (`audit_log/validated` + `slack_post.delivered_at` populated): PASS — both deliver within ≤10s of validate commit.
- **F.3.4** (≥95% lane-by-lane consistency): PASS at **100%** (12/12 lanes match across Run 1↔2 and Run 1↔3, comparing UN/LOCODE origin + destination + equipment_type signature).
- **F.3.5** (3 consecutive without wedged failure): PASS.

`slack_post` rows delivered to `#solvo-onramp-demo` with `delivered=true` on all three runs — Defect 15 confirmed closed.
`upload_result` rows (Phase 6.8 §6.2) delivered on all three runs; signed-URL GET returns HTTP 200 on the first attempt every time, no drain race observed.

### Mechanical patch applied in-flight (not a defect, documented for transparency)

Run 2 and Run 3 hit `error: duplicate_input_hash` on the original fixture because `OnrampJob.input_hash` is computed from raw file bytes only — same fixture submitted twice collapses to the first job_id by idempotency design. Mechanically patched by writing two byte-distinct fixture copies (modified `wb.properties.description` only — no cell touched) and uploading each under the canonical filename. Cross-run consistency was still 100% so no lane data was perturbed by the metadata-only change.

This is NOT a defect that requires a fix for shipping. It is a smoke-test artifact: three independent runs of the **identical** content are not actually a meaningful regression test because the system correctly collapses them. The legitimate three-run consistency check is what F.3.4 measures (lane-by-lane signature stability across submissions of distinguishable but materially equivalent inputs), and that passed at 100%. Hafeedh may wish to update the V7 prompt template to generate distinct fixtures upfront in future smoke passes.

---

## What halted

### Defect 16 — Rules-engine rule precedence masks F.4 expected rule_ids

The three F.4 fixtures all produce rejections, but `validity_window_in_the_past` fires first on every fixture and masks the rule_ids the F.4 milestones expect.

| Fixture | Status | Rejected | Expected rule_id | Actual rule_id(s) | Verdict |
|---|---|---|---|---|---|
| `broken_impossible_port_codes.xlsx` | completed (70s) | 2 | `port_unknown_unlocode` (≥2) | `validity_window_in_the_past` ×2 | **FAIL** |
| `broken_negative_rates.xlsx` | completed (61s) | 4 | `negative_base_rate` (≥1) | `validity_window_in_the_past` ×3, `negative_base_rate` ×1 | PASS (1 of 4 hits the expected rule) |
| `broken_malformed_edifact.edi` | completed (22s) | 1 | classifier-fail OR EDIFACT structural citation | `validity_window_in_the_past` ×1 | **FAIL** |

**Root cause hypothesis (read-only investigation needed before fixing).** The three "broken" fixtures all appear to also carry past validity windows, and the deterministic rules engine evaluates the validity-window rule before the port-vocabulary rule and the EDIFACT-structural rule. Once a lane is rejected on validity, the later rules never get a chance to attribute the *real* defect the fixture was designed to surface.

Two legitimate fixes — Hafeedh chooses:

1. **Fixture refresh (preferred).** Edit `fixtures/broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, and `broken_malformed_edifact.edi` so their validity windows are in the future, leaving the *intended* defect (impossible UN/LOCODE, negative rate, malformed EDIFACT) as the surviving rejection cause. This preserves the rules-engine precedence as a deliberate semantic ("don't waste compute on stale data") and keeps the F.4 test exercising what its name claims.
2. **Rule re-ordering.** Inside `packages/ingest/rules_engine.py`, change the order so `port_unknown_unlocode` and EDIFACT structural rules fire before the validity-window rule. This is the heavier path because it touches Stage 4 deterministic logic (Phase 4 spec) and would require updating the audit-trail expectations in any test that pins rule ordering. Path 1 is the right one unless there is a separate reason to re-rank.

Path 1 touches no code and no invariants — it is fixture-only and the V8 build (or a Hafeedh direct-ops commit) can land it without re-running Phase 6.X review cycles. Path 2 touches the rules engine and requires re-running unit tests + arguably a Phase 6.9 spec patch.

### Defect 17 — `rejection_reason` and `lane_id` always null on rejected records

Every rejected record across all three F.4 fixtures has `rejection_reason: null` and `lane_id: null` in the normalized output JSON. The `rule_id` field populates correctly. The schema accepts both fields as nullable, but the F.4 milestone documentation and the audit-trail expectations (Master PRD §3.3 "deterministically rejected with rule-ID provenance") imply they should populate.

Sample (from Run-bpc `result_bpc.json`):

```json
{
  "rule_id": "validity_window_in_the_past",
  "rejection_reason": null,
  "lane_id": null
}
```

**Root cause hypothesis.** `packages/ingest/rules_engine.py:apply_hard_rules` builds the `deterministically_rejected` list but either (a) the rule callbacks never set `rejection_reason` / `lane_id` on the `RejectedLane` Pydantic instance they emit, or (b) a downstream `model_copy(update=...)` in `_validate` drops the fields by re-emitting only `rule_id`. The fact that `lane_id` is null on EVERY rejection — including the correctly-cited `negative_base_rate` row — suggests this is a population bug in the rules engine itself, not a downstream stripping.

This is independent of Defect 16. Even after fixture refresh, the empty `rejection_reason` will still be empty unless the rules engine is patched.

**Fix scope.** Single function in `packages/ingest/rules_engine.py`. Likely 6-12 lines per rule callback to populate `rejection_reason` and pass through the originating `lane_id`. New unit test under `tests/unit/test_rules_engine.py` to lock in the fields. No schema change.

This is design-judgment work — design of the rejection-record contract — and per the V7 halt rule belongs in a follow-up spec (call it Phase 6.9 closure patch).

---

## Stage F.5 — NOT RUN

F.5 was gated on F.4 passing all three milestones. Halted before exercising the admin audit endpoint. F.5 readiness is independent of Defects 16 + 17 (no code changes from those defects touch the audit-trail emission path), so a V8 resume can run F.5 directly against the existing job rows from this V7 attempt without re-running F.1-F.3.

---

## Vertex AI spend this run

Three full Pro ensembles × 12 normalized lanes + one Flash extract per F.3 run + Flash extracts on three F.4 fixtures. Rough estimate: ~$2.40 (well under the $5 halt ceiling). Cumulative across V3-V7 is approximately $14. No spend gate breach.

---

## Recommended path forward

1. **V8 spec — Phase 6.9 closure patch.** Two scoped fixes:
   - **F.4 fixture refresh** for `broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi` — move validity windows into the future so the *named* defect surfaces as the surviving rule_id (Defect 16, Path 1).
   - **`packages/ingest/rules_engine.py` rejection-record population** — emit `rejection_reason` text + `lane_id` on every `RejectedLane` (Defect 17).
   - Unit-test additions: one assertion per broken fixture lane that the correct rule_id is the *first* rejection, plus one test that every rejected record has non-null `rejection_reason` + `lane_id`.

2. **V8 resume Step 4** with just F.4 + F.5 (F.1-F.3 already PASSED at this V7 attempt, no re-run needed). Smoke spend should drop to ~$0.30 because no F.3 reruns.

3. After F.4 + F.5 pass: write `BUILD_COMPLETE_V4.md` (or whatever closure name the spec ladder calls for) and authorize demo recording.

---

## Confirmed unchanged by V7

- All Phase 6.5 / 6.6 / 6.8 invariants intact. F.3 × 3 with 100% determinism is the strongest evidence we have ever generated of that.
- `slack_post` delivery to `#solvo-onramp-demo` works (Defect 15 truly closed).
- `upload_result` outbox flow works end-to-end (Phase 6.8 §6.2 truly closed).
- Signed-URL fetch returns 200 first-attempt every time (no upload_result drain race observed in practice).
- Channel rename does not regress any of 148 unit tests.

— End of HUMAN_INTERVENTION_REQUEST_V7.md.
