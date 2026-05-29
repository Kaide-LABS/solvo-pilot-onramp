# PHASE 9 SPEC — Live-Stack Closure Patch (Defect 21, post-V10)

**Output of Step 2 (Phase 9 spec generation).** Consumes the Step 4 V10 halt at commit `3081627` (`HUMAN_INTERVENTION_REQUEST_V10.md`) and the BUILD_COMPLETE_V7 closure record at `bab8f04` (Phase 8 approval at `cb4102b`, Phase 8 implementation at `e2acab8`). Feeds a single Step 3A build cycle, a single Step 3B review cycle, then a V11 Stage F.4–F.5 resume. F.3 does NOT re-run; V7 results stand. After Phase 9 lands and V11 F.4 + F.5 passes, Sprint 2 closure is FINAL and demo recording is authorized.

---

## §0 — Phase Plan Header

*This is Phase 9 of the Sprint 2 build — the closure patch following the Step 4 V10 halt at commit `3081627` (HUMAN_INTERVENTION_REQUEST_V10.md). Phase 8 closed Defects 19 + 20 at the Stage 2 schema gate (`extract_excel_payload` pre-scan + `ValidationError` → `ExtractionError` wrap) and at the Stage 4 R1 re-injection (`_validate` synthesizes carrier `LaneRecord` instances and runs `apply_hard_rules` on them). That machinery is **correct and verified live at V10** — the 51s `broken_impossible_port_codes` job completed cleanly, the Defect 20 wrap did not trip, and no `ValidationError` was raised. The failure is one layer upstream: Flash silently omitted the two shape-violating rows (A4 `ZZ@ZZ`, A6 `QQ@QQ`) from `body["lanes"]` (lane-ID gap `1,2,4` with no `3` is the evidence), so the Phase 8 pre-scan had no work to do.*

*Phase 9 closes Defect 21 by moving shape-violation detection upstream of Flash. A deterministic, pre-LLM scan over the cell list identifies origin/destination columns by header label and lifts shape-violating cells out before the prompt is rendered. The Phase 8 post-LLM `_pre_scan_shape_violators` is retained as fallback for unlabeled-column ratesheets where column roles can only be inferred semantically by the LLM. The conflicting Phase 7 §6.1.2 prompt clause is deleted; `PROMPT_VERSION` is bumped. After Phase 9 + V11 F.4–F.5 pass, Sprint 2 closure is FINAL.*

### Scope

- **Defect 21 — Phase 7 §6.1.2 prompt conflict; Flash omits shape-violating rows under live conditions.** SYSTEM_INSTRUCTIONS contains two clauses Flash reads as conflicting: line 28 ("If a row cannot be confidently extracted as a lane, omit it. Do NOT guess.") and lines 29–32 ("Lanes with shape-violating port codes ... MUST be included in `lanes` ... Do NOT omit them."). Flash chose the safer rule and dropped A4 + A6. Resolution: a hybrid pre-LLM + post-LLM scan architecture in which the primary path is deterministic Python over the cell list (LLM-independent) and the secondary path is the retained Phase 8 post-LLM scan (for genuinely messy ratesheets where headers don't identify port columns). The conflicting prompt bullet is deleted because the primary path no longer requires Flash to pass through bad data; the structural "omit non-lane rows" rule is preserved (now unconflicted). `PortCode`'s regex stays. The Phase 8 Stage 4 re-injection in `_validate` stays — it reads `normalized.shape_violating_lanes` regardless of which path populated it.

**The architectural decision is locked.** The V10 halt doc recommended a prompt rewrite; that recommendation is rejected. Prompt rewrites have failed three times (Defects 18a, 18b, 21). Phase 9 removes Flash's discretion from shape-violation detection for the labeled-column case entirely. Code-inspection story: bad-data handling is hardcoded Python rules on a known cell schema, not an LLM instruction — the System Resilience pillar made literal.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 9.** Per ULTIMATE_PRD §4.7, provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 9 introduces no new academic claims.

---

## §1 — Files Added or Modified

### Modified

- `packages/ingest/excel_extractor.py` — **MODIFIED**. Add `_identify_port_columns(cells: list[dict[str, Any]]) -> dict[str, dict[int, int]] | None` (or the 3A agent's structurally equivalent shape) that walks the cell list, locates the header row per sheet (the lowest `row` for each `sheet` value containing a string cell), and returns a per-sheet mapping `{sheet_title: {origin_col: int, destination_col: int}}` when both an origin-role header and a destination-role header are present. Header matching is **case-insensitive** against the canonical label set: `{"origin", "origin_port", "pol", "load_port", "load port", "port_of_loading", "port of loading"}` for origin and `{"destination", "destination_port", "pod", "discharge_port", "discharge port", "port_of_discharge", "port of discharge"}` for destination. Returns `None` when ANY sheet present in the cell list lacks both identifiable columns (signalling fallback). Add `_scan_cells_for_shape_violators(cells: list[dict[str, Any]], column_map: dict[str, dict[int, int]]) -> tuple[list[dict[str, Any]], list[ShapeViolatingLane]]` that, given the identified columns, walks every cell whose `(sheet, col)` matches an origin or destination column slot at a non-header row, checks the value against `_UNLOCODE_SHAPE` (the existing module-level regex from Phase 8), and for any violating row builds a `ShapeViolatingLane` with the **real `coord`** (e.g. `A4`, `B6`) as the `source_row_reference.cell_reference`. The returned surviving-cell list has ALL cells belonging to a violator's row removed (origin, destination, equipment, base_rate, validity — i.e. every cell with the same `sheet` and `row` as the violating port cell), so Flash never sees the bad row at all. `extract_excel_payload` is rewired: (1) build cell list as today; (2) call `_identify_port_columns`; (3) if it returns a column map, call `_scan_cells_for_shape_violators`, replace the cell list with the surviving subset, and stash the lifted violators in a local; if it returns `None`, both locals are empty (signalling pure-fallback); (4) render the prompt with the surviving cell list; (5) call Flash; (6) call the existing `_pre_scan_shape_violators` on the resulting `body["lanes"]` (Phase 8 fallback, retained verbatim); (7) **merge** the pre-LLM violators with the post-LLM violators using dedup-by-(`lane_id` if present else `(sheet, row)`-tuple from `source_row_reference`); (8) write the union into `body["shape_violating_lanes"]`; (9) the rest of `extract_excel_payload` (force-overwrite + Defect 20 wrap + `model_validate`) runs unchanged. Internal note for the 3A agent: the `lane_id` field on a pre-LLM violator is synthesized as `f"shape_violator_{sheet}_{row}"` for traceability and dedup; the post-LLM path may produce a different `lane_id` (Flash-supplied) for the same physical row, so the dedup key must fall back to `(sheet, row)` from `source_row_reference` when the IDs differ.

- `packages/ingest/prompts.py` — **MODIFIED**. Delete the four-line bullet at lines 29–32 ("Lanes with shape-violating port codes ... Stage 4 validation will reject them ..."). Rewrite the line-28 bullet from confidence-based ("If a row cannot be confidently extracted as a lane, omit it. Do NOT guess.") to **structurally** anchored: `- Omit a row only when it contains no lane data at all — for example, blank rows, section headers, or rows missing both port columns AND the rate column. If a row has a port column populated, emit a lane for it.` This preserves the original protection (don't invent lanes from header rows or empty cells) while removing the conflict the V10 evidence exposed. Bump `PROMPT_VERSION` from `"stage2.excel.v1"` to `"stage2.excel.v2"`. The rest of `SYSTEM_INSTRUCTIONS` (cell-shape preamble, no-invention rule, UN/LOCODE format guidance, equipment_type enum, empty-containers clause, schema_version pin) is **unchanged**.

- `tests/integration/test_stage_pipeline_mocked.py` — **MODIFIED**.
  - Add `test_pre_llm_scan_identifies_labeled_origin_destination_columns`. Constructs a synthetic cell list mirroring the `broken_impossible_port_codes.xlsx` layout (sheet `Rates`; header row 1 with `origin`/`destination`/`equipment`/`base_rate_usd`/`validity_start`/`validity_end`; five data rows including A4=`ZZ@ZZ` and B6=`QQ@QQ`). Asserts `_identify_port_columns` returns `{"Rates": {"origin_col": 1, "destination_col": 2}}` (or equivalent), and `_scan_cells_for_shape_violators` returns a surviving cell list with no cell whose `(row, sheet)` is `(4, "Rates")` or `(6, "Rates")`, plus a violators list of length 2 with `source_row_reference.cell_reference` exactly `"A4"` and `"B6"` (real coordinates, not positional synthesis).
  - Add `test_pre_llm_scan_falls_back_when_columns_unlabeled`. Constructs a cell list with no recognizable origin/destination headers (e.g. headers are `col1`/`col2`/`col3`). Asserts `_identify_port_columns` returns `None` and the orchestrator surfaces an empty pre-LLM violator list, leaving the Phase 8 post-LLM fallback to handle whatever Flash returns.
  - Add `test_pre_llm_scan_handles_partial_sheet_coverage`. Multi-sheet workbook where ONE sheet has labeled origin/destination and ANOTHER has unlabeled columns. Per the spec rule "returns `None` when ANY sheet lacks both identifiable columns," the orchestrator MUST fall back rather than partial-scan — assert the empty pre-LLM list and that the post-LLM path is the sole arbiter.
  - **REWRITE `test_full_pipeline_broken_impossible_port_codes`** to the V10-faithful contract. Mock `_generate_with_retry` to return a body that contains **only the three clean lanes** Flash actually returned at V10 (`L1: DEHAM→USNYC`, `L2: NLRTM→SGSIN`, `L4: USLAX→JPYOK`) — explicitly NOT the two violators. Use the synthetic cell-list mock injection that includes all five rows. Assert: (a) the pre-LLM scan lifted 2 violators with real cell coords `A4` and `B6`; (b) `payload.shape_violating_lanes` has length 2 (pre-LLM only — post-LLM fallback returns empty because Flash already omitted them); (c) `payload.lanes` has length 3 from Flash (matching V10 live behavior); (d) the existing Stage 4 re-injection mirror still produces 2 `port_unknown_unlocode` rejections with `cell_reference` exactly `"A4"` and `"B6"`. **This is the central test of Phase 9: shape-violation detection must work even when Flash is fully uncooperative.**
  - `test_extract_excel_payload_wraps_validation_error_as_extraction_error` (Phase 8 Defect 20 guard) — UNCHANGED.
  - `test_normalizer_carveout_handles_table_unknown_shape_valid_codes` (Phase 8) — UNCHANGED.
  - `test_full_pipeline_broken_malformed_edifact`, `test_full_pipeline_writes_audit_log`, `test_tasks_module_wires_audit_row_into_all_success_paths`, `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source` — UNCHANGED.

### Added

The two new helper functions (`_identify_port_columns`, `_scan_cells_for_shape_violators`) live inside `packages/ingest/excel_extractor.py` alongside the Phase 8 `_pre_scan_shape_violators`. No new module files. No new schema files (`ShapeViolatingLane` from Phase 8 is reused as-is). No new fixtures (the synthetic cell-list mocks in the integration tests cover the labeled and unlabeled cases without touching the on-disk `.xlsx`).

### Deleted

None. All prior closure records, halt records, and spec files remain.

---

## §2 — Pip Dependencies

**None.** Phase 9 is pure-Python logic + prompt edit + test work.

---

## §3 — Pydantic Schemas

**No schema changes.** `ShapeViolatingLane` (Phase 8) is reused without modification:

```python
class ShapeViolatingLane(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lane_id: str = Field(min_length=1, max_length=64)
    raw_origin_code: str = Field(min_length=1, max_length=64)
    raw_destination_code: str = Field(min_length=1, max_length=64)
    source_row_reference: SourceRow
```

The pre-LLM path populates `lane_id = f"shape_violator_{sheet}_{row}"`, `raw_origin_code` / `raw_destination_code` directly from the cell `value`s (coerced to `str` and bounded to the field's `max_length=64`), and `source_row_reference` from the real cell coordinate (`sheet_name=cell.sheet`, `row_number=cell.row`, `cell_reference=cell.coord`). Build Directive 1 from Phase 8 (real Excel provenance, not positional synthesis) is satisfied **natively** by the primary path — the cell list already carries true coordinates from `_build_cell_list`.

`NormalizedRatesheet.shape_violating_lanes: list[ShapeViolatingLane] = Field(default_factory=list)` — unchanged.

`PortCode.code: Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$", ...)` — unchanged. The white-box anchor stays.

---

## §4 — FastAPI Route Signatures

**No route changes.** The pre-LLM violators flow through `extract_excel_payload`'s existing return path and surface in `OnrampOutput.normalized_payload` via the same JSONB column Phase 8 used. The result-url endpoint's response shape is unchanged.

---

## §5 — Alembic Migration

**No new migration.** No schema change.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 21 Fix: Hybrid Pre-LLM + Post-LLM Shape Detection

**Stage 2 (`packages/ingest/excel_extractor.py`):**

After `cells = await asyncio.to_thread(_build_cell_list, file_path)` and before prompt rendering, insert:

```python
# Phase 9 §6.1 (Defect 21): deterministic pre-LLM shape scan on labeled-column
# workbooks. The cell list already carries true coordinates from
# _build_cell_list, so the lifted violators inherit real Excel provenance
# without any positional synthesis (Build Directive 1 from Phase 8 is native here).
column_map = _identify_port_columns(cells)
pre_llm_violators: list[ShapeViolatingLane] = []
if column_map is not None:
    cells, pre_llm_violators = _scan_cells_for_shape_violators(cells, column_map)
```

`_identify_port_columns` walks the cell list once, building a per-sheet view `{sheet_title: list[cell]}`, finds the minimum `row` per sheet that contains at least one string cell (the header row), and for each header cell normalises the string value (`value.strip().lower()`) and looks it up in the origin and destination label sets. Returns the column-index mapping only if EVERY sheet present in the cell list has BOTH an origin column and a destination column identified. Otherwise returns `None` (entire workbook falls back). The 3A agent makes the all-sheets-must-resolve rule explicit because a partial scan creates a silent-correctness trap: a violator on the unlabeled sheet would slip through.

`_scan_cells_for_shape_violators(cells, column_map)`:
1. Build a set `violating_rows: set[tuple[str, int]]` (sheet, row).
2. For each cell whose `sheet` is in `column_map` and whose `col` equals either `column_map[sheet]["origin_col"]` or `column_map[sheet]["destination_col"]`, and whose `row` is greater than the header row for that sheet, check `_UNLOCODE_SHAPE.match(str(cell.value))`. If it fails, add `(sheet, row)` to `violating_rows`.
3. For each `(sheet, row)` in `violating_rows`, find the origin-column cell and destination-column cell on that row (if either is absent, treat its value as the empty string) and emit one `ShapeViolatingLane` with `lane_id = f"shape_violator_{sheet}_{row}"`, the two raw codes, and the origin cell's `coord` (or the destination cell's `coord` if origin is absent) as the `cell_reference`.
4. Return `(surviving_cells, violators)` where `surviving_cells` is `cells` filtered to exclude every cell whose `(sheet, row)` is in `violating_rows`.

After Flash returns:

```python
# Phase 8 §6.1 fallback path — retained verbatim. When the pre-LLM scan was
# unable to identify port columns (column_map is None), this is the SOLE
# detector; when the pre-LLM scan ran, this catches anything Flash leaked
# despite the cleaner upstream input.
post_llm_violators = _pre_scan_shape_violators(body, sheet_label)
```

Then merge with dedup:

```python
# Phase 9 §6.1: union the two violator sources. Dedup key is
# (sheet_name, row_number) from source_row_reference — robust against
# lane_id divergence between the pre-LLM synthetic ID and any Flash-supplied ID.
seen: set[tuple[str, int]] = set()
combined: list[ShapeViolatingLane] = []
for v in (*pre_llm_violators, *post_llm_violators):
    key = (v.source_row_reference.sheet_name, v.source_row_reference.row_number)
    if key in seen:
        continue
    seen.add(key)
    combined.append(v)
```

The rest of `extract_excel_payload` runs as today — `body["shape_violating_lanes"] = [v.model_dump(mode="json") for v in combined]`, then Phase 7 §6.1.1 force-overwrite of `conformal_scores` / `flagged_for_review` / `deterministically_rejected`, then the Defect 20 `try/except ValidationError` wrap around `NormalizedRatesheet.model_validate(body)`.

**Stage 4 (`packages/ingest/tasks.py:_validate`):** **UNCHANGED.** The synthetic-carrier re-injection block from Phase 8 reads `normalized.shape_violating_lanes` and runs `apply_hard_rules` on the carriers regardless of which path populated the field. Phase 9 simply guarantees the field is populated.

### §6.2 — Prompt Edit

`packages/ingest/prompts.py`:

- Delete the bullet at lines 29–32 (the four-line "shape-violators MUST be included" block).
- Replace the line-28 bullet with the structural formulation: `- Omit a row only when it contains no lane data at all — for example, blank rows, section headers, or rows missing both port columns AND the rate column. If a row has a port column populated, emit a lane for it.`
- Bump `PROMPT_VERSION = "stage2.excel.v1"` → `PROMPT_VERSION = "stage2.excel.v2"`.

All other lines of `SYSTEM_INSTRUCTIONS` are byte-identical.

### §6.3 — Test Re-architecture

The four mocked-pipeline tests landing in this phase are detailed under §1. The critical test is the rewritten `test_full_pipeline_broken_impossible_port_codes`: the Flash mock returns **only the three clean lanes** Flash actually returned at V10 — no violators. The test must STILL end with `len(payload.shape_violating_lanes) == 2`, both having `cell_reference` equal to the real Excel coords `A4` and `B6` respectively, and the mirrored Stage 4 re-injection must emit 2 `port_unknown_unlocode` rejections. This is the V10-faithful contract: the fix CANNOT depend on Flash's cooperation.

---

## §7 — Cross-Phase Integration Requirements

Phase 9 must NOT break:

- **Phase 6.5 per-task `make_async_engine`.** Untouched.
- **Phase 6.6 per-call `get_vertex_client`.** Untouched.
- **Phase 6.6 `_failure_payload` / `_commit_failure`.** Untouched. The Defect 20 wrap from Phase 8 still routes Pydantic violations through `_commit_failure`.
- **Phase 6.8 success-path transactional outbox.** Untouched. `shape_violating_lanes` rides the existing `OnrampOutput.normalized_payload` JSONB column. No new outbox row, no new transaction.
- **Phase 6.9 `RejectionRecord` schema** (`source_row_reference`, `lane_id`, `rule_id`, `rule_description`). Synthetic R1 rejections emitted from re-injected pre-LLM violators populate all four — `cell_reference` is the real `A4` / `B6`, not a positional `A2` / `A3`.
- **Phase 6.9 R1..R7 precedence and `apply_hard_rules` public signature.** Untouched.
- **Phase 7 §6.1.1 force-overwrite** in `excel_extractor`. Stays. Phase 9's pre-LLM scan runs against `cells`, not against `body[...]`, so it is upstream of both Flash and the force-overwrite.
- **Phase 7 §6.1.2 prompt contract.** The "shape-violators MUST be in lanes" clause is DELETED (dead weight under the new architecture). The "omit non-lane rows" clause is REWORDED structurally. `PROMPT_VERSION` is bumped. This is the only intentional invariant change in Phase 9 — and the prompt contract was never load-bearing because Flash already proved (V10) that it would not be obeyed.
- **Phase 7 §6.1.3 normalizer carve-out** at `normalizer.py:265–298`. Stays as documented at Phase 8 — defense-in-depth for the shape-valid + table-unknown case.
- **Phase 7 §6.2 EDIFACT DTM override.** Untouched.
- **Phase 7 §6.3 inline `OnrampAuditLog` writes.** Untouched.
- **Phase 7 §6.4 mocked test module.** Three new tests added; one Phase-8-era test rewritten; the other five retained verbatim.
- **Phase 7 §11 canonical rule_id literal set.** Synthetic R1 rejections still emit `port_unknown_unlocode` — canonical.
- **Phase 8 §6.1 Stage 4 re-injection in `_validate`.** UNCHANGED. Reads `normalized.shape_violating_lanes` regardless of population path.
- **Phase 8 §6.1 post-LLM `_pre_scan_shape_violators`.** UNCHANGED in behaviour. Now runs as the fallback when `_identify_port_columns` returns `None`, and as a secondary detector when the pre-LLM path already ran.
- **Phase 8 §6.2 Defect 20 `ValidationError` → `ExtractionError` wrap.** UNCHANGED.
- **F.3 happy-path test.** No expected change — K+N has labeled columns, the pre-LLM scan emits empty (no shape-violators), the post-LLM fallback also emits empty; downstream behavior identical. F.3 does NOT re-run; V7 results stand.
- **Defect 6 regression test.** Untouched.
- **§3.10 retention posture.** No retention contract change.
- **Anti-Replication boundary.** Pre-LLM scan is pure-Python regex matching against a fixed label set; no LLM, no pricing logic.

---

## §8 — Phase 9 Acceptance Criteria

3A build + 3B review approve when ALL true:

1. **Pre-LLM column identifier present:** `packages/ingest/excel_extractor.py` contains `_identify_port_columns`. Walks the cell list, normalises header strings case-insensitively, recognises the documented origin and destination label set, returns per-sheet column indices or `None`. Static inspection.
2. **Pre-LLM shape scan present:** `_scan_cells_for_shape_violators` exists. Operates on the cell list, uses the existing `_UNLOCODE_SHAPE` regex, builds `ShapeViolatingLane` with the real cell `coord` as `cell_reference`, removes every cell on a violating row from the surviving cell list. Static inspection.
3. **Pre-LLM scan called before Flash:** `extract_excel_payload` invokes `_identify_port_columns` then `_scan_cells_for_shape_violators` BEFORE `_build_prompt` / `_generate_with_retry`. Static inspection.
4. **All-sheets-resolve rule enforced:** `_identify_port_columns` returns `None` when any sheet in the cell list lacks an identifiable origin or destination column. Test-covered.
5. **Post-LLM fallback retained:** `_pre_scan_shape_violators` from Phase 8 is unchanged in signature and behaviour and still runs after Flash on `body["lanes"]`. Static inspection.
6. **Union + dedup:** `body["shape_violating_lanes"]` is populated from the union of pre-LLM + post-LLM violators, deduped by `(sheet_name, row_number)` of `source_row_reference`. Static inspection.
7. **Prompt clause deleted:** `SYSTEM_INSTRUCTIONS` no longer contains the "shape-violators MUST be included in `lanes`" four-line bullet. Grep verification.
8. **Omit clause reworded structurally:** the line that previously said "If a row cannot be confidently extracted as a lane, omit it" is replaced with the structural formulation in §6.2. Grep verification.
9. **`PROMPT_VERSION` bumped** to `"stage2.excel.v2"`. Grep verification.
10. **`PortCode` schema unchanged:** `packages/core/models/ratesheet.py:51` retains `pattern=r"^[A-Z]{2}[A-Z0-9]{3}$"`. Static inspection.
11. **`ShapeViolatingLane` unchanged:** identical to Phase 8; reused. Static inspection.
12. **Phase 8 Stage 4 re-injection untouched:** `packages/ingest/tasks.py:_validate` reads `normalized.shape_violating_lanes` unchanged. Static inspection.
13. **Phase 7 §6.1.1 force-overwrite preserved and still direct-assignment.** Static inspection.
14. **Phase 6.9 RejectionRecord provenance:** the rewritten test's mirrored re-injection produces 2 rejections with `source_row_reference.cell_reference` equal to `"A4"` and `"B6"` (NOT positional `A2`/`A3`/`A5`). Test-covered.
15. **V10-faithful test passes:** `test_full_pipeline_broken_impossible_port_codes` mocks Flash to return ONLY the 3 clean lanes V10 observed and STILL produces `len(payload.shape_violating_lanes) == 2` + 2 `port_unknown_unlocode` rejections. This is the central regression detector for Defect 21.
16. **Three new pre-LLM tests pass:** column identification, fallback on unlabeled headers, fallback on partial-coverage multi-sheet workbook.
17. **F.3 happy-path test unchanged** — verify `tests/integration/test_pipeline_e2e.py` does not appear in the Phase 9 diff.
18. **`pytest tests/unit -q` passes** baseline plus any new unit coverage for the helpers.
19. **`pytest tests/integration -q` passes** all mocked-pipeline tests (rewritten + new + retained).
20. **`ruff check .` clean.**
21. **`ruff format --check .` clean.**
22. **`mypy --strict` clean on changed files.** Pre-existing `retention.py` / `signed_url.py` / `test_ratesheet_models.py` errors remain out-of-scope per §9.
23. **No new secrets in the diff.**
24. **V11 F.4–F.5 readiness.** Phase 9 acceptance does NOT require running V11.

---

## §9 — Explicit NON-GOALS for Phase 9

- **No `PortCode` schema relaxation.** Regex stays.
- **No new rules in `apply_hard_rules`.** R1..R7 set locked.
- **No `BUILD_COMPLETE_V8.md` written by Phase 9 itself.** That lands after V11 F.4-F.5 actually passes.
- **No retention.py / signed_url.py / test_ratesheet_models.py mypy cleanup.**
- **No K+N fixture regeneration.**
- **No `broken_impossible_port_codes.xlsx` fixture regeneration** — the on-disk fixture is correct; Phase 9 changes detection, not test data.
- **No Master PRD or ULTIMATE_PRD prose changes.**
- **No `PHASE_10_SPEC.md`.** Phase 9 is intended as the final closure patch for Sprint 2.
- **No new outbox event types.**
- **No deletion of prior closure records, halt records, or spec files.**
- **No backfill of historical `OnrampOutput.normalized_payload` blobs.** Forward-only; `default_factory=list` handles old blobs cleanly.
- **No re-running of F.3.** F.3 V7 results stand.
- **No changes to `RejectionRecord` schema.** Phase 6.9 shape locked.
- **No changes to the dispatcher's `deliver_audit_log`.** Phase 7 §6.3 contract preserved.
- **No removal of the Phase 7 §6.1.3 normalizer carve-out.**
- **No removal of the Phase 8 post-LLM `_pre_scan_shape_violators`.** Retained as fallback.
- **No removal of the Phase 8 Defect 20 `ValidationError` wrap.**
- **No new env var.**

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_8_SPEC.md`.
- Do NOT modify any `BUILD_COMPLETE*.md` file.
- Do NOT modify any `HUMAN_INTERVENTION_REQUEST*.md` file.
- Do NOT modify `Solvo_Master_PRD.md` or `ULTIMATE_PRD.md`.
- Do NOT modify the F.3 happy-path test or the Defect 6 regression test.
- Do NOT touch R1..R7 precedence or `apply_hard_rules` public signature.
- Do NOT add a new rule.
- Do NOT introduce a new env var.
- Do NOT change `OnrampAuditLog` schema or its migration.
- Do NOT modify the K+N happy-path fixture or the `broken_impossible_port_codes` fixture.
- Do NOT relax `PortCode`'s regex pattern.
- Do NOT remove the Phase 7 §6.1.3 normalizer carve-out.
- Do NOT remove the Phase 8 post-LLM `_pre_scan_shape_violators` or the Defect 20 wrap.
- Do NOT modify `_validate`'s Stage 4 re-injection block — it reads `shape_violating_lanes` and is correct.
- Do NOT modify the Phase 8 `ShapeViolatingLane` schema or the `NormalizedRatesheet.shape_violating_lanes` field.

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`. Phase 9 adds no new models.
- All Vertex AI calls bind to `location='global'` with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation.
- Container-boot validators fail-fast on misconfiguration.
- Anti-Replication boundary: no pricing, POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing, no rate / margin / recommendation computation.
- Transactional outbox row counts unchanged. `shape_violating_lanes` rides the existing `OnrampOutput.normalized_payload` JSONB column.
- Redis distributed locks use `SET NX EX`.
- N=3 Pro ensemble at temperatures `(0.1, 0.5, 0.9)` with majority-vote consensus.
- Per-task `make_async_engine` (Phase 6.5) preserved.
- Per-call `get_vertex_client` (Phase 6.6) preserved.
- Deterministic Stage 1 + Stage 4 — zero LLM calls in `classify_format` or in `apply_hard_rules` or any of its R1..R7 branches.
- Phase 7 §11 canonical rule_id literal set — pre-LLM-lifted shape-violators are re-injected at Stage 4 by Phase 8's unchanged `_validate` block and emit `rule_id="port_unknown_unlocode"`, canonical.
- Phase 8 §11 carrier-pattern invariant — `model_construct` is used exclusively inside the Stage 4 re-injection (production) and in tests for synthesizing sentinel R1 inputs. No new `model_construct` usage in Phase 9 outside that scope.
- **NEW Phase 9 invariant**: shape-violation detection MUST have a deterministic, LLM-independent primary path for any workbook whose origin/destination columns are identifiable by header label. The LLM is never the sole gate for shape-violation detection on labeled-column workbooks. Integration tests proving shape-violation handling MUST mock the LLM to return only clean lanes (the V10-observed behaviour) and still produce the expected `shape_violating_lanes` + R1 rejections via the deterministic path. Tests that rely on Flash including violators in its mock body are forbidden as the sole proof of the contract — they may exist as supplementary coverage, but the V10-faithful test is the load-bearing one.

— End of PHASE_9_SPEC.md.
