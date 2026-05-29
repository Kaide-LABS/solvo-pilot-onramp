# HUMAN_INTERVENTION_REQUEST_V10 — Step 4 V10 F.4 HALTED

**Halt reason.** Step 4 Stage F.4 re-run against the post-Phase-8 stack (HEAD `bab8f04`) surfaced a new failure mode on `broken_impossible_port_codes.xlsx` that is NOT the V9 schema defect Phase 8 closed. Pre-scan + Defect 20 wrap are live and correctly wired, but Flash silently omitted the shape-violating rows from `body["lanes"]`, so the pre-scan had nothing to lift and Stage 4 emitted zero R1 rejections. This is a prompt-adherence defect (Defect 21) that requires design judgment + touches the Phase 7 §6.1.2 prompt invariant → mandatory halt per V10 rule.

---

## Stack under test

- Repo HEAD: `bab8f04` (BUILD_COMPLETE_V7.md)
- Phase 8 review approval: `cb4102b`
- Phase 8 implementation: `e2acab8`
- Pre-flight artifacts all present:
  - `_pre_scan_shape_violators` (2 refs), `_coerce_source_row_reference` (2 refs), `shape_violating_lanes` (3 refs) in `excel_extractor.py`
  - `stage2_schema_violation` (1 ref) — Defect 20 wrap live
  - `shape_violating_lanes` (2 refs) + `model_construct` (5 refs) in `tasks.py` — Stage 4 re-injection live
  - `class ShapeViolatingLane` (1) + `shape_violating_lanes` (1) in `ratesheet.py`
  - `PortCode.code` regex `^[A-Z]{2}[A-Z0-9]{3}$` (1 match) — unchanged
- All 4 boot validators pass on `/v1/health`.

## What happened

- Job `597fcf8363c346afa63a2c8a2fb5cfcd` reached `status=completed` in 51s (well under 260s budget) — Defect 20 wrap not triggered, no stuck-at-extracting.
- Final payload counts: `normalized=2`, `flagged=1`, `rejected=0`, `shape_violating=0`.
- Lanes Flash returned:
  - `lane_id=1`  DEHAM → USNYC (src `A2`) — clean row A2 ✓
  - `lane_id=2`  NLRTM → SGSIN (src `A3`) — clean row A3 ✓
  - `lane_id=4`  USLAX → JPYOK (src `A5`) — clean row A5, surfaced as `port_obfuscation_unresolved` flag because `JPYOK` passes UN/LOCODE regex but isn't in `un_locode_reference` (the carve-out's live-reachable arm; behaving as Phase 8 closure documented).
- **Lanes Flash dropped: A4 (`ZZ@ZZ` → `USLAX`) and A6 (`DEHAM` → `QQ@QQ`).** Note the lane numbering jumps `1,2,4` — Flash internally tracked row 4 but emitted it from the source row A5, indicating it consciously skipped A4 and A6.

## Why this isn't a Phase 8 regression

Phase 8 closed two specific failures:
- Defect 19 (Stage 3 carve-out unreachable in production) — the fix was a Stage 2 pre-scan that lifts shape-violators out of `body["lanes"]` before `model_validate`. **The fix is correct, the pre-scan ran, and it found nothing — because `body["lanes"]` had no shape-violators to find.**
- Defect 20 (`ValidationError` not caught) — the fix wraps `model_validate(body)` and converts to `ExtractionError`. **No `ValidationError` was raised, because the pre-scanned body validated cleanly.**

The Phase 8 code is doing exactly what the spec said it would. The failure is one layer upstream: the LLM never put the bad rows into `body["lanes"]` in the first place.

## Root cause — prompt conflict in `packages/ingest/prompts.py:SYSTEM_INSTRUCTIONS`

The current prompt contains two instructions that conflict on shape-violating rows:

```text
- If a row cannot be confidently extracted as a lane, omit it. Do NOT guess.
- Lanes with shape-violating port codes (e.g. 'ZZ@ZZ', 'foo', '12345') MUST be
  included in `lanes` with the port code passed through unchanged. Do NOT
  reject them at extraction. Do NOT omit them. Stage 4 validation will reject
  them with deterministic rule citations.
```

Flash interprets `ZZ@ZZ` as a code it "cannot confidently extract as a lane" (first rule) and silently omits it, never reaching the second rule. The two clauses need to be re-ordered + the first one needs an explicit carve-out for shape-violators, or the contract needs to change so that shape-violators are surfaced via a separate `body` field that doesn't depend on Flash's judgment about "confidence."

## Defect 21 (new)

**Defect 21 — Phase 7 §6.1.2 prompt conflict: Flash omits shape-violating rows under live conditions.** The two prompt clauses ("omit if you can't confidently extract" vs "shape-violators MUST be in lanes") are interpreted as a conflict in which the first wins. Pre-scan therefore receives a `body["lanes"]` with shape-violators already removed and emits zero `shape_violating_lanes`. Stage 4 R1 has nothing to fire on. The end-user-visible failure is "BPC silently completes with zero rejections" — worse than V9, which at least surfaced a stuck job; this run loses the bad lanes entirely.

This is design judgment + a Phase 7 §6.1.2 invariant touch → mandatory halt.

## Recommended Phase 9 closure shape (for spec generation)

A single phase, one source file changed plus one new test:

1. **Rewrite `SYSTEM_INSTRUCTIONS` in `packages/ingest/prompts.py`** to remove the conflict. Suggested patch:
   - Replace the current "If a row cannot be confidently extracted as a lane, omit it" bullet with a narrower formulation: "If a row's structure does not contain a lane at all (no origin/destination/rate columns), omit it. Do NOT guess at missing values." — anchored on row STRUCTURE, not on code VALIDITY.
   - Strengthen the shape-violating bullet: "If origin or destination contains ANY text — even nonsense like 'ZZ@ZZ', 'foo', '12345', or unrecognized codes — emit the lane with the port code passed through verbatim. This is non-negotiable. Stage 4 will reject these with canonical citations; your job is only to extract them, not to judge them." Add an explicit positive example showing that A4=`ZZ@ZZ` MUST appear in `lanes`.
   - Bump `PROMPT_VERSION` so audit-trail records reflect the change.
2. **Confirm the new prompt is the only behavioral change.** No schema changes, no route changes, no migration, no new dependency, no Phase 8 logic touched.
3. **Add a Phase-9-specific test** that locks Flash in via the response-schema mock so any future prompt refactor can't silently regress prompt-adherence (the failure here only surfaced live; the mocked test passed because the mock body explicitly included the violators).
4. **Re-run V11 F.4 + F.5** against the new prompt. F.3 still does not need to re-run.
5. **Anti-regression note for the spec author.** The "omit unconfident rows" clause exists for a real reason — to protect against Flash inventing lanes from header rows or empty cells. The replacement language must preserve that protection while carving shape-violators out.

## What stands from prior runs

- F.3 happy-path V7 results — UNCHANGED.
- F.4 `broken_negative_rates` (BNR) V9 PASS — UNCHANGED.
- F.4 `broken_malformed_edifact` (BME) V9 PASS — UNCHANGED.
- F.5 audit-trail V9 PASS — NOT re-run this cycle (gated on F.4 completing cleanly).

## What did NOT happen

- No Defect 19 regression. Pre-scan + Stage 4 re-injection are live and correct; they just had no work to do because the input was empty of shape-violators.
- No Defect 20 regression. No `ValidationError` was raised; no job stuck at `extracting`.
- No infra fault, no DNS race after `up -d --wait`, no boot-validator failure.
- No Vertex spend overrun (single 51s job at gemini-3.1-flash-lite + gemini-3.1-pro-preview ensemble; well under $5 ceiling).
- No invariant outside Phase 7 §6.1.2 needs to move.

## Diagnosis evidence

Raw fixture (`fixtures/broken_impossible_port_codes.xlsx`, sheet `Rates`):

```
A1 origin    B1 destination  C1 equipment  D1 base_rate_usd  E1 validity_start  F1 validity_end
A2 DEHAM     B2 USNYC        40HC          2100              2026-06-01         2026-12-31
A3 NLRTM     B3 SGSIN        40HC          1850              2026-06-01         2026-12-31
A4 ZZ@ZZ     B4 USLAX        40HC          2450              2026-06-01         2026-12-31   ← omitted by Flash
A5 USLAX     B5 JPYOK        20GP          1750              2026-06-01         2026-12-31
A6 DEHAM     B6 QQ@QQ        40HC          2200              2026-06-01         2026-12-31   ← omitted by Flash
```

Flash output (`payload.lanes`): lane_ids `1, 2, 4` — rows A2, A3, A5. Rows A4 and A6 silently dropped. `payload.shape_violating_lanes`: `[]`.

The lane-ID gap (`1, 2, 4` with no `3`) is the smoking gun: Flash internally enumerated all 5 data rows but emitted only three of them. The omission was deliberate, not a transcription mistake.

## Handoff

Step 2 (spec generation) author: please consume this halt doc and produce `PHASE_9_SPEC.md` per the recommended shape above. Step 3A (Codex build) re-runs only after the spec lands. Step 4 V11 re-runs F.4 + F.5 only; F.3 still stands.

Demo recording remains BLOCKED until V11 F.4 passes with at least one `port_unknown_unlocode` rejection carrying real Excel cell provenance.

— Step 4 V10 halt, 2026-05-29.
