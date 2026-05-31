# BUILD_COMPLETE_V8 — Sprint 2 Closure (post Phase 9)

**Closure record for Phase 9.** Defect 21 closed. Sprint 2 build is FINAL pending Step 4 V11 Stage F.4–F.5 re-run. F.3 happy-path V7 results stand and do NOT re-run. BNR + BME passed at V9 and stand.

Phase 9 implementation landed at `ce3adcb`; Step 3B QA review approved at `081a569`. **No fix patches were required** — the implementation passed every §8 acceptance criterion and every documented critique on inspection.

---

## Defect 21 closed — and why the seam is removed, not patched

**Defect 21 — Phase 7 §6.1.2 prompt conflict; Flash omits shape-violating rows under live conditions.** At V10, the 51s `broken_impossible_port_codes` job completed cleanly, but Flash silently dropped the two shape-violating rows (A4 `ZZ@ZZ`, B6 `QQ@QQ`) from `body["lanes"]`. The smoking gun was the lane-ID gap `1,2,4` with no `3`. Flash read two SYSTEM_INSTRUCTIONS clauses as conflicting — line 28 ("omit rows you can't confidently extract") versus lines 29–32 ("shape-violators MUST be included") — and chose the safer omit rule. The Phase 8 post-LLM `_pre_scan_shape_violators` then had no work to do, because the violators were never in `body["lanes"]` to begin with.

**Why this is a removed seam, not a patched one.** The prior three attempts (Defects 18a, 18b, 21) all tried to make Flash behave via prompt wording. Each failed because the detection of bad data was *gated on an LLM instruction* — a non-deterministic seam. Phase 9 removes that seam for the labeled-column case entirely by relocating shape-violation detection **upstream of Flash**, into deterministic Python over the cell list:

1. `_identify_port_columns(cells)` walks the cell list, finds each sheet's header row by **case-insensitive label match** against the canonical origin/destination label sets (not "lowest string row"), and returns per-sheet `{origin_col, destination_col, header_row}` — or `None` if **any** sheet lacks identifiable headers (all-sheets-resolve rule; a partial scan would be a silent-correctness trap).
2. `_scan_cells_for_shape_violators(cells, column_map)` checks every origin/destination cell at a data row against `_UNLOCODE_SHAPE`, builds a `ShapeViolatingLane` carrying the **real Excel coordinate** (`A4`, `B6`) as `cell_reference`, and **removes every cell on a violating row** from the surviving cell list so Flash physically never sees the bad row.

Because the cell list already carries true coordinates from `_build_cell_list`, the lifted violators inherit real Excel provenance natively — no positional synthesis. The LLM is no longer the sole gate for shape-violation detection on any labeled-column workbook. This is the System Resilience pillar made literal: bad-data handling is hardcoded Python rules on a known cell schema, not an LLM instruction Flash is free to disobey.

The Phase 8 post-LLM `_pre_scan_shape_violators` is **retained verbatim** as the fallback for genuinely messy ratesheets where column roles can only be inferred semantically (header labels absent). The two sources are unioned and deduped.

---

## Phase 9 fix descriptions

1. **Pre-LLM deterministic scan (`packages/ingest/excel_extractor.py`).** Two new module-level functions added alongside the Phase 8 `_pre_scan_shape_violators`:
   - `_identify_port_columns(cells) -> dict[str, dict[str, int]] | None` — label-matched header detection against `_ORIGIN_LABELS` / `_DESTINATION_LABELS` frozensets; returns per-sheet column indices + header row, or `None` (fallback) if any sheet is unresolvable. A banner/title row above the real headers does not misidentify columns — the search continues past non-label rows until it finds a row carrying BOTH labels.
   - `_scan_cells_for_shape_violators(cells, column_map) -> (surviving_cells, violators)` — lifts violating rows with real `coord` provenance and strips every cell on those rows from the surviving list.
   - `extract_excel_payload` rewired: build cell list → `_identify_port_columns` → if non-`None`, `_scan_cells_for_shape_violators` (replace cells, stash `pre_llm_violators`) → render prompt → Flash → post-LLM `_pre_scan_shape_violators` → union + dedup → force-overwrite + Defect 20 wrap + `model_validate` (all unchanged downstream).

2. **B6-not-A6 destination anchor pin.** In `_scan_cells_for_shape_violators`, the `anchor_cell` (which supplies `cell_reference`) is pinned from the **violating** side (`origin_cell or dest_cell`, where both initially hold only cells that failed the regex) **before** the recovery loop fills in the non-violating side's `raw_*_code`. When the destination is the violator (B6) and the origin (A6) is valid, `cell_reference` is correctly `B6`, while `raw_origin_code` still recovers the real A6 value. Verified in code and asserted in the V10-faithful test (`by_row[6].cell_reference == "B6"`, `raw_origin_code == "DEHAM"`).

3. **Prompt clause deletion + structural reword (`packages/ingest/prompts.py`).** The four-line "shape-violators MUST be included in `lanes`" bullet (the conflict source) is deleted. The line-28 confidence-based omit bullet ("If a row cannot be confidently extracted as a lane, omit it") is rewritten structurally: "Omit a row only when it contains no lane data at all — blank rows, section headers, or rows missing both port columns AND the rate column. If a row has a port column populated, emit a lane for it." `PROMPT_VERSION` bumped `stage2.excel.v1` → `stage2.excel.v2`. All other `SYSTEM_INSTRUCTIONS` lines byte-identical.

4. **Post-LLM fallback retained (`_pre_scan_shape_violators`).** Unchanged signature and behaviour. Now runs as the sole detector when `_identify_port_columns` returns `None`, and as a belt-and-suspenders secondary detector when the pre-LLM path already ran (expected to return empty, since Flash never saw the lifted rows).

5. **Union + dedup.** `body["shape_violating_lanes"]` is populated from `(*pre_llm_violators, *post_llm_violators)` deduped by `(source_row_reference.sheet_name, source_row_reference.row_number)` — robust against `lane_id` divergence between the pre-LLM synthetic ID (`shape_violator_<sheet>_<row>`) and any Flash-supplied ID.

6. **`cell_count` metadata fidelity.** `cell_count_for_metadata = len(cells)` is captured immediately after `_build_cell_list`, **before** the pre-LLM scan trims violating rows, so the audit record reflects the true workbook size, not the post-trim size.

7. **Stage 4 re-injection (`packages/ingest/tasks.py:_validate`) — UNCHANGED.** Reads `normalized.shape_violating_lanes` regardless of which path populated it, synthesizes `LaneRecord` carriers via `model_construct`, and runs `apply_hard_rules` so R1 emits canonical `port_unknown_unlocode` rejections. Confirmed absent from the Phase 9 diff.

---

## Critique 4 (min_length=1 space sentinel) — judgment: ACCEPTABLE

`ShapeViolatingLane.raw_origin_code` / `raw_destination_code` carry `min_length=1`. When a violating row has an empty origin or destination, the pre-LLM path fills that field with a single space: `(origin_value or " ")[:64]`.

**This does NOT mask a classification error.** The decisive fact is `_build_cell_list` ([excel_extractor.py:341-342](packages/ingest/excel_extractor.py#L341-L342)): cells with `value is None` are **skipped** and never enter the cell list. Therefore:

- A fully empty or no-port row has **no cells** in the list → it can never enter `violating_rows` → it is never mis-lifted as a shape-violator. Critique 4(c) concern is not realizable.
- The lift is only ever triggered by a **present** origin/destination cell whose value fails `_UNLOCODE_SHAPE`. The sentinel only ever fills the *opposite* side of an already-confirmed violator row — it is a field-population placeholder, not a classification driver.
- Critique 4(b): an empty port cell is never *itself* classified as a shape-violation; classification is driven entirely by present, regex-failing cells.

**One cosmetic edge case is documented (not blocking, not in fixture scope).** In an empty-origin + garbage-destination row, the sentinel sets `origin_port.code = " "`, and R1's origin-first precedence fires on the space — emitting `rule_description` "origin port code ' ' does not match the UN/LOCODE shape" while the anchor `cell_reference` correctly points at the destination cell. This is a mild description/anchor attribution inconsistency. It does NOT occur in `broken_impossible_port_codes.xlsx` (both violator rows have one valid + one garbage port, no empties), the rejection is still canonical (`rule_id="port_unknown_unlocode"`), and the cited cell is still correct. Per spec §9 (no fixture regeneration) it is out of Phase 9 scope; flagged here for optional future hardening (e.g. attribute R1 to the side that actually failed, or emit a distinct missing-value rule for empty ports).

---

## §8 Acceptance criteria — all 24 verified

| # | Criterion | Result |
|---|-----------|--------|
| 1 | `_identify_port_columns` present, label-matched | ✓ |
| 2 | `_scan_cells_for_shape_violators` present, real `coord`, row-strip | ✓ |
| 3 | Pre-LLM scan called BEFORE `_build_prompt` / `_generate_with_retry` | ✓ |
| 4 | All-sheets-resolve → `None` (partial-coverage test) | ✓ |
| 5 | Post-LLM `_pre_scan_shape_violators` retained, unchanged | ✓ |
| 6 | Union + dedup by `(sheet_name, row_number)` | ✓ |
| 7 | "shape-violators MUST be included" bullet deleted | ✓ |
| 8 | Omit clause reworded structurally | ✓ |
| 9 | `PROMPT_VERSION = "stage2.excel.v2"` | ✓ |
| 10 | `PortCode` regex unchanged (`ratesheet.py:51`) | ✓ |
| 11 | `ShapeViolatingLane` unchanged | ✓ |
| 12 | `_validate` Stage 4 re-injection untouched | ✓ |
| 13 | Phase 7 §6.1.1 force-overwrite preserved, direct-assignment | ✓ |
| 14 | Re-injection cites `A4` / `B6` (not positional) | ✓ |
| 15 | **V10-faithful test** — Flash mock has only 3 clean lanes, still 2 violators + 2 rejections | ✓ |
| 16 | Three new pre-LLM tests pass (+ banner-row test) | ✓ |
| 17 | F.3 `test_pipeline_e2e.py` absent from Phase 9 diff | ✓ |
| 18 | `pytest tests/unit` — 153 passed | ✓ |
| 19 | `pytest tests/integration` — 11 passed / 12 infra-skipped | ✓ |
| 20 | `ruff check` clean (changed files) | ✓ |
| 21 | `ruff format --check` clean (changed files) | ✓ |
| 22 | `mypy --strict` clean on `excel_extractor.py` + `prompts.py` | ✓ |
| 23 | No new secrets in diff | ✓ |
| 24 | V11 not required for acceptance | ✓ |

**Autonomous critiques verified: 4/4** — (1) label-matching header detection with banner-row degradation test; (2) violator-row cells excluded from Flash input, asserted via `captured_prompt_cells`; (3) B6-not-A6 destination anchor pin; (4) space sentinel judged ACCEPTABLE.

---

## Commits / SHAs

| Step | SHA |
|------|-----|
| Phase 9 implementation | `ce3adcb` |
| Phase 9 fix patches | none required |
| Phase 9 review approved | `081a569` |
| BUILD_COMPLETE_V8 (this record) | (this commit) |

---

## Cloud Run

URL unchanged. Phase 9 is code-only — no infra, no migrations, no env vars. A redeploy (`cloudbuild submit` against current `main`) is required to ship the Phase 9 extractor + prompt changes before the V11 F.4–F.5 re-run.

---

## Out-of-scope pre-existing failures (carried forward, NOT blocking)

- 6 mypy errors in `packages/lifecycle/retention_enforcer.py` / `packages/compliance/retention.py`.
- 1 mypy error in `packages/storage/signed_url.py:51`.
- 3 `dict-item` mypy errors in `tests/unit/test_ratesheet_models.py`.

All pre-date Phase 9 and are explicitly out-of-scope per spec §9 NON-GOALS and §8 criterion 22.

## Stray file

`_v8_test_broken.sh` is an untracked local scratch file — confirmed NOT committed in `ce3adcb` and NOT tracked at HEAD. No action.

---

## Handoff to Hafeedh

**Step 4 V11 Stage F.4–F.5 final re-run authorized** against the post-Phase-9 stack at HEAD (`ce3adcb` implementation + `081a569` approval + this closure commit), after a Cloud Run redeploy.

- **F.3 does NOT re-run** — V7 results stand.
- **BNR + BME passed at V9 and stand.**
- **Only `broken_impossible_port_codes` needs re-test under F.4.**
- If **V11 F.4 + F.5 PASS**, demo recording is authorized for Vidyard with Isaac. Sprint 2 closure is then FINAL.
- If F.4 or F.5 surfaces a new live-stack defect, halt and write `HUMAN_INTERVENTION_REQUEST_V11.md`.

---

## Defect lineage 1–21 with closure SHAs

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
| 18a | `4a1a257` | Phase 7 closure (BUILD_COMPLETE_V6) |
| 18b | `4a1a257` | Phase 7 closure |
| 18c | `4a1a257` | Phase 7 closure |
| 18d | `4a1a257` | Phase 7 closure |
| 19 | `e2acab8` | Phase 8 closure (BUILD_COMPLETE_V7) |
| 20 | `e2acab8` | Phase 8 closure |
| 21 | `ce3adcb` | Phase 9 closure (this record); approved `081a569` |

— Step 3B (review) handoff, 2026-05-31. Sprint 2 complete pending V11 F.4–F.5.
