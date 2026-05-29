# PHASE 8 SPEC — Live-Stack Closure Patch (Final, post-V9)

**Output of Step 2 (Phase 8 spec generation).** Consumes the Step 4 Stage F.4 halt at commit `6cd502f` (`HUMAN_INTERVENTION_REQUEST_V9.md`) and the BUILD_COMPLETE_V6 closure record at `378323b`. Feeds a single Step 3A build cycle, a single Step 3B review cycle, then a V10 Stage F.4-F.5 resume (F.3 does NOT need to re-run; V7 results stand). After Phase 8 lands and V10 F.4-F.5 passes, Sprint 2 closure is FINAL and demo recording is authorized.

---

## §0 — Phase Plan Header

*This is Phase 8 of the Sprint 2 build — the final closure patch following the Step 4 Stage F.4 halt at commit `6cd502f` (HUMAN_INTERVENTION_REQUEST_V9.md). Phase 7 closed Defects 18a/b/c/d at the schema and tooling level but introduced a test-architecture blind spot — the Phase 7 §6.4 mocked tests bypassed Stage 2's Pydantic gate via `PortCode.model_construct(...)` while claiming to exercise the post-18a contract. V9 surfaced this when the live stack hit `ZZ@ZZ` / `QQ@QQ` and the job stuck at `extracting`. Phase 8 closes Defects 19 + 20 and re-architects the Phase 7 §6.4 mocked tests to exercise the actual Stage 2 Pydantic gate. After Phase 8 lands and V10 F.4-F.5 passes, Sprint 2 closure is FINAL.*

### Scope

- **Defect 19 — Phase 7 §6.1.3 Stage 3 normalizer carve-out unreachable in production.** `PortCode.code: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$", ...)` rejects shape-violating codes at `NormalizedRatesheet.model_validate(body)` in `extract_excel_payload`, before Stage 3 ever sees the lane. Resolution: Option D from the halt doc — pre-scan `body["lanes"]` in `extract_excel_payload` BEFORE `model_validate`, lift shape-violators into a separate `shape_violating_lanes` collection, surface them at `_validate` as direct inputs to `apply_hard_rules` so R1 fires with the canonical `port_unknown_unlocode` rule_id. The `PortCode` schema and the Phase 7 prompt contract both remain intact.
- **Defect 20 — `pydantic.ValidationError` not in `_extract`'s exception catcher.** Independent of Defect 19, any Pydantic violation at Stage 2 currently leaves the job at `status=extracting` indefinitely. Resolution: wrap `extract_excel_payload`'s `model_validate(body)` in a try/except that converts `ValidationError` → `ExtractionError`. `_extract`'s existing `except (ExcelTooLargeError, ExtractionError)` handler then catches it and calls `_commit_failure` with the canonical failure-audit row.
- **Test-architecture re-architecture — Phase 7 §6.4 mocked tests exercise the live schema gate.** `test_full_pipeline_broken_impossible_port_codes` must submit the actual `fixtures/broken_impossible_port_codes.xlsx` through Stage 2 (with Vertex LLM mocked but Pydantic gates active) and assert end-to-end `status=completed` with R1 rejections. `test_stage3_normalizer_passes_shape_violating_ports_to_stage4` becomes redundant under the pre-scan approach (the carve-out at `normalizer.py:265-275` stays as defense-in-depth for table-unknown shape-valid codes, but it's no longer the load-bearing path for shape-violators) and is removed.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 8.** Per ULTIMATE_PRD §4.7, provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 8 introduces no new academic claims.

---

## §1 — Files Added or Modified

### Modified

- `packages/ingest/excel_extractor.py` — **MODIFIED**. After the LLM returns `body` and before `NormalizedRatesheet.model_validate(body)`, insert a pre-scan loop that walks `body["lanes"]`, identifies any row where `lane["origin_port"]["code"]` or `lane["destination_port"]["code"]` fails the regex `^[A-Z]{2}[A-Z0-9]{3}$`, and lifts them into a separate `shape_violating_lanes: list[dict[str, Any]]` collection. The pre-scan emits an internal `ShapeViolatingLane(BaseModel)` (or equivalent) carrying the raw port codes + the source_row_reference + the rule_id that R1 will emit. The function signature continues to return `(payload: NormalizedRatesheet, metadata: ExtractionMetadata)` — `shape_violating_lanes` is surfaced as a field on `NormalizedRatesheet` so it flows through the existing persistence path. The model_validate call is also wrapped in a try/except to convert `ValidationError` → `ExtractionError` (Defect 20 fix).
- `packages/core/models/ratesheet.py` — **MODIFIED (one schema add)**. Add a new `ShapeViolatingLane(BaseModel)` schema with `model_config = ConfigDict(extra="forbid")` and fields: `lane_id`, `raw_origin_code`, `raw_destination_code`, `source_row_reference`. Also add `shape_violating_lanes: list[ShapeViolatingLane] = Field(default_factory=list)` to `NormalizedRatesheet`. Do NOT modify `PortCode` itself.
- `packages/ingest/tasks.py` — **MODIFIED**. `_extract` requires no signature change — the `shape_violating_lanes` field on `NormalizedRatesheet` is persisted automatically through the existing `insert_output` path. `_validate` reads `normalized.shape_violating_lanes`, synthesizes `LaneRecord` instances via `LaneRecord.model_construct(...)` + `PortCode.model_construct(...)`, wraps them in a synthetic `NormalizedRatesheet`, runs `apply_hard_rules` on the synthetic set, then merges the resulting `deterministically_rejected` entries into the main `validated` ratesheet. R1 fires on the synthetics and emits the canonical `port_unknown_unlocode` rule_id.
- `packages/ingest/normalizer.py` — **MODIFIED (cleanup, not new fix)**. The Phase 7 §6.1.3 shape-check carve-out at lines 265-275 stays as defense-in-depth for the table-unknown shape-valid case (e.g., the LLM extracts a valid-shape but unknown UN/LOCODE like `XXAAA`). The carve-out's docstring/comments are updated to reflect that shape-violators now never reach Stage 3 (they're pre-scanned out at Stage 2); the carve-out's actual reachable scope is now narrower.
- `tests/integration/test_stage_pipeline_mocked.py` — **MODIFIED**.
  - `test_full_pipeline_broken_impossible_port_codes` is rewritten to submit the actual `fixtures/broken_impossible_port_codes.xlsx` through `extract_excel_payload` (with `get_vertex_client` mocked to return the LLM body the live stack would return — bad-shape codes in `lanes`). Asserts end-to-end: the pre-scan lifts the violators into `payload.shape_violating_lanes`, `_validate` re-injects them, `apply_hard_rules` emits R1 rejections, the final `OnrampOutput`-equivalent carries them. **NO `PortCode.model_construct(...)` in the test body.**
  - `test_stage3_normalizer_passes_shape_violating_ports_to_stage4` is **DELETED**. The carve-out remains in the code as defense-in-depth, but the load-bearing path for shape-violators is now the pre-scan, not the carve-out. A new test `test_normalizer_carveout_handles_table_unknown_shape_valid_codes` is added to cover the carve-out's remaining responsibility (table-unknown shape-valid case).
  - `test_full_pipeline_writes_audit_log` and `test_tasks_module_wires_audit_row_into_all_success_paths` retained unchanged.
  - `test_full_pipeline_broken_malformed_edifact` retained unchanged.
  - `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source` retained, BUT updated to assert R1 fires on the pre-scanned shape-violators (so the assertion is "Stage 4 emits canonical rule_ids regardless of whether the violator came from a real `LaneRecord` or a synthesized one"). The "zero LLM calls in Stage 4" assertion stays.

### Added

- The `ShapeViolatingLane` schema (in `ratesheet.py`) and the `test_normalizer_carveout_handles_table_unknown_shape_valid_codes` test mentioned above. No other additions.

### Deleted

None. All prior closure records, halt records, and spec files remain.

---

## §2 — Pip Dependencies

**None.** Phase 8 is pure logic + schema work.

---

## §3 — Pydantic Schemas

### `ShapeViolatingLane` (new)

```python
class ShapeViolatingLane(BaseModel):
    """Lane lifted from Stage 2 because its port codes failed UN/LOCODE shape.

    Pre-scan output: shape-violating codes are routed around `LaneRecord`
    (which enforces the strict regex via `PortCode`) and surfaced at
    `_validate` as direct R1 inputs. Stage 4 emits `port_unknown_unlocode`
    rejections with the same rule_id + canonical rule_description.
    """

    model_config = ConfigDict(extra="forbid")

    lane_id: str = Field(min_length=1, max_length=64)
    raw_origin_code: str = Field(min_length=1, max_length=64)
    raw_destination_code: str = Field(min_length=1, max_length=64)
    source_row_reference: SourceRow
```

`extra="forbid"` preserved. The 3A agent verifies the exact field set is what `_validate` needs to construct a synthetic `LaneRecord` (via `PortCode.model_construct(...)`) that feeds `apply_hard_rules` correctly. Note: this is the ONE place where `model_construct` is legitimate — synthesizing a sentinel value for R1 to reject.

### `NormalizedRatesheet.shape_violating_lanes` (new field)

```python
class NormalizedRatesheet(BaseModel):
    # ... existing fields ...
    shape_violating_lanes: list[ShapeViolatingLane] = Field(default_factory=list)
```

`default_factory=list` keeps backwards compat with any pre-Phase-8 `OnrampOutput.normalized_payload` blobs (the JSONB field deserializes cleanly even if the new key is absent).

### `PortCode` — UNCHANGED

`packages/core/models/ratesheet.py:51` retains `code: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$", min_length=5, max_length=5)`. The white-box anchor stays.

---

## §4 — FastAPI Route Signatures

**No route changes.** The pre-scan output flows through `_validate` and surfaces in the existing `OnrampOutput.normalized_payload` JSONB column. The `deterministically_rejected` array (already returned by the result-url endpoint) gains the R1 entries naturally.

---

## §5 — Alembic Migration

**No new migration.** The new `shape_violating_lanes` field is JSONB-nested in `OnrampOutput.normalized_payload`; no DB schema change.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 19 Fix: Stage 2 Pre-Scan + Stage 4 Re-Injection

**Stage 2 (`packages/ingest/excel_extractor.py`):**

After the LLM returns `body` and before the force-overwrite of empty containers (Phase 7 §6.1.1), insert the pre-scan loop:

```python
import re
from typing import Final
from pydantic import ValidationError

from packages.core.models.ratesheet import ShapeViolatingLane, SourceRow

_UNLOCODE_SHAPE: Final = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")


def _pre_scan_shape_violators(
    body: dict[str, Any],
    sheet_name: str,
) -> list[ShapeViolatingLane]:
    """Lift shape-violating lanes out of body['lanes'] before model_validate.

    Phase 8 §6.1 (Defect 19): PortCode's regex rejects shape-violators at
    model_validate, so the Phase 7 §6.1.3 normalizer carve-out is unreachable.
    Pre-scanning here lifts them out cleanly and routes them to _validate as
    direct R1 inputs.
    """
    surviving: list[dict[str, Any]] = []
    violating: list[ShapeViolatingLane] = []
    for idx, lane in enumerate(body.get("lanes", [])):
        origin_code = lane.get("origin_port", {}).get("code", "")
        dest_code = lane.get("destination_port", {}).get("code", "")
        if not _UNLOCODE_SHAPE.match(origin_code) or not _UNLOCODE_SHAPE.match(dest_code):
            violating.append(
                ShapeViolatingLane(
                    lane_id=lane.get("lane_id", f"shape_violator_{idx}"),
                    raw_origin_code=origin_code,
                    raw_destination_code=dest_code,
                    source_row_reference=SourceRow(
                        sheet_name=sheet_name,
                        row_number=idx + 2,  # +1 for header, +1 for 1-indexed
                        cell_reference=f"A{idx + 2}",
                    ),
                )
            )
        else:
            surviving.append(lane)
    body["lanes"] = surviving
    return violating
```

Then in `extract_excel_payload`, after building `body`:

```python
# ... existing body construction ...
sheet_label = workbook.sheetnames[0] if workbook.sheetnames else "Rates"
shape_violating = _pre_scan_shape_violators(body, sheet_label)

# Phase 7 §6.1.1: force-overwrite (unchanged)
body["conformal_scores"] = {}
body["flagged_for_review"] = []
body["deterministically_rejected"] = []
body["shape_violating_lanes"] = [v.model_dump(mode="json") for v in shape_violating]

# Phase 8 §6.2 (Defect 20): wrap model_validate to surface ValidationError
# as ExtractionError so the failure-handler catches it.
try:
    payload = NormalizedRatesheet.model_validate(body)
except ValidationError as exc:
    raise ExtractionError(f"stage2_schema_violation: {exc.error_count()} error(s)") from exc

return payload, metadata
```

**Stage 4 (`packages/ingest/tasks.py:_validate`):**

After `apply_hard_rules` runs on the normal lanes, re-inject the shape-violators:

```python
# ... existing _validate body ...
validated, violations = apply_hard_rules(normalized)

# Phase 8 §6.1: synthesize LaneRecord instances for shape-violators and
# re-run apply_hard_rules on them so R1 emits canonical port_unknown_unlocode.
shape_violators = normalized.shape_violating_lanes
if shape_violators:
    from datetime import date
    from decimal import Decimal
    from packages.core.models.ratesheet import LaneRecord, PortCode

    synthetic_lanes = [
        LaneRecord.model_construct(
            lane_id=sv.lane_id,
            origin_port=PortCode.model_construct(code=sv.raw_origin_code),
            destination_port=PortCode.model_construct(code=sv.raw_destination_code),
            equipment_type="40HC",  # sentinel — R1 fires before any equipment check
            commodity_code=None,
            base_rate_usd=Decimal("0"),  # sentinel
            surcharges=[],
            transit_time_days=None,
            validity_start=date.today(),
            validity_end=date.today(),
            source_row_reference=sv.source_row_reference,
        )
        for sv in shape_violators
    ]
    synthetic_rs = NormalizedRatesheet(
        job_id=validated.job_id,
        prospect_id=validated.prospect_id,
        extraction_metadata=validated.extraction_metadata,
        lanes=synthetic_lanes,
    )
    synthetic_validated, synthetic_violations = apply_hard_rules(synthetic_rs)
    validated = validated.model_copy(
        update={
            "deterministically_rejected": (
                list(validated.deterministically_rejected)
                + list(synthetic_validated.deterministically_rejected)
            )
        }
    )
    violations = list(violations) + list(synthetic_violations)
```

The 3A agent verifies this works against `apply_hard_rules`'s actual signature (`apply_hard_rules(rs, *, now=None) -> tuple[NormalizedRatesheet, list[RuleViolation]]` per Phase 6.9) and that the `model_construct` bypass on `LaneRecord` doesn't cause downstream issues. The bypass is necessary because the synthetic lane has known-bad port codes that real validation would reject — we're using `LaneRecord` as a carrier shape for R1's input, not as a "real" lane.

### §6.2 — Defect 20 Fix: ValidationError → ExtractionError

Already shown in §6.1 above. The wrap is one try/except around `model_validate(body)` in `extract_excel_payload`. The fix is small and absorbed alongside Defect 19's pre-scan logic. The existing `_extract`'s `except (ExcelTooLargeError, ExtractionError)` handler then routes through `_commit_failure` per the Phase 6.6 §6.3 contract.

### §6.3 — Test Re-architecture

In `tests/integration/test_stage_pipeline_mocked.py`:

**REWRITE `test_full_pipeline_broken_impossible_port_codes`:**

```python
def test_full_pipeline_broken_impossible_port_codes() -> None:
    """Phase 8 §6.3 — Stage 2 pre-scan lifts shape-violators, Stage 4 R1 emits canonical rejection.

    Exercises the LIVE schema gate (no PortCode.model_construct bypass at the
    test entry point). Submits the actual broken_impossible_port_codes.xlsx
    fixture through extract_excel_payload with Vertex mocked to return
    bad-shape codes in `lanes`. Asserts the pre-scan lifts them into
    payload.shape_violating_lanes, then synthesizes the Stage 4 re-injection
    and verifies apply_hard_rules emits R1 rejections with canonical rule_ids.
    """
    from pathlib import Path
    import asyncio
    from packages.ingest import excel_extractor as ex
    from packages.ingest.rules_engine import apply_hard_rules
    # ... mock get_vertex_client to return a body containing ZZ@ZZ / QQ@QQ
    # ... call extract_excel_payload(...) for real, including model_validate
    # ... assert len(payload.shape_violating_lanes) >= 2
    # ... build the synthetic ratesheet per §6.1 and run apply_hard_rules
    # ... assert every synthetic rejection has rule_id == "port_unknown_unlocode"
    # ... and lane_id + rule_description populated
```

The 3A agent fills the implementation. The test must NOT use `PortCode.model_construct(...)` in any assertion path — that's the bypass we're moving away from. `model_construct` may still appear inside the production code path being exercised (Phase 8 §6.1's synthetic LaneRecord), but not in the test body itself.

**DELETE `test_stage3_normalizer_passes_shape_violating_ports_to_stage4`** and add:

```python
def test_normalizer_carveout_handles_table_unknown_shape_valid_codes() -> None:
    """Phase 8 §6.3 — Stage 3 carve-out's narrower responsibility post-pre-scan.

    Shape-VALID but table-UNKNOWN codes (e.g. 'XXAAA' which passes regex but
    isn't in un_locode_reference) hit the carve-out and pass through to
    Stage 4. Stage 4 R1 does NOT fire on these (R1 checks shape only); the
    lane stays in `lanes` for Phase 5 conformal scoring to evaluate.
    """
    # ... build lane with PortCode(code="XXAAA") via normal validation
    # ... mock resolve_port_code to return canonical=None
    # ... assert carve-out lets the lane through to final_lanes
    # ... assert R1 does NOT fire (shape passes the regex)
```

The remaining tests (`test_full_pipeline_writes_audit_log`, `test_tasks_module_wires_audit_row_into_all_success_paths`, `test_full_pipeline_broken_malformed_edifact`, `test_stage4_invariant_apply_hard_rules_is_sole_rejection_source`) stay; the last one is updated to assert R1 fires on pre-scanned shape-violators per §1.

---

## §7 — Cross-Phase Integration Requirements

Phase 8 must NOT break:

- **Phase 6.5 per-task `make_async_engine`.** Untouched.
- **Phase 6.6 per-call `get_vertex_client`.** Untouched.
- **Phase 6.6 `_failure_payload` / `_commit_failure`.** The Defect 20 fix surfaces ValidationError as ExtractionError, which feeds `_commit_failure` per the existing contract. Failure-path audit row writes (Phase 7 §6.3) trigger correctly.
- **Phase 6.8 success-path transactional outbox.** Untouched. The `shape_violating_lanes` data flows through the existing `OnrampOutput.normalized_payload` JSONB column — no new outbox row, no new transaction.
- **Phase 6.9 `RejectionRecord` schema** (source_row_reference, lane_id, rule_id, rule_description). The synthetic R1 rejections emitted from re-injected shape-violators populate all four fields correctly.
- **Phase 6.9 R1..R7 precedence and `apply_hard_rules` public signature.** Untouched.
- **Phase 7 §6.1.1 force-overwrite** in excel_extractor. Stays. Phase 8's pre-scan runs BEFORE the force-overwrite of `conformal_scores` / `flagged_for_review` / `deterministically_rejected` (because the pre-scan operates on `body["lanes"]`, not on those fields).
- **Phase 7 §6.1.2 prompt instruction** that bad-shape codes flow into `lanes`. Stays. The LLM continues to be told to include them; the pre-scan handles them downstream.
- **Phase 7 §6.1.3 Stage 3 carve-out** at `normalizer.py:265-275`. Stays as defense-in-depth for table-unknown shape-valid codes (the new narrower scope per §6.3 above).
- **Phase 7 §6.2 EDIFACT DTM override.** Untouched.
- **Phase 7 §6.3 inline OnrampAuditLog writes.** Untouched.
- **Phase 7 §6.4 mocked test module.** Two tests rewritten/replaced per §6.3; other 4 tests untouched.
- **Phase 7 §11 canonical rule_id literal set invariant.** The R1 rejection emitted from re-injected shape-violators has `rule_id="port_unknown_unlocode"` — canonical.
- **F.3 happy-path test.** No expected change — K+N doesn't have shape-violators in its lanes; pre-scan emits empty `shape_violating_lanes` collection; downstream behavior is identical.
- **Defect 6 regression test.** Untouched.
- **§3.10 retention posture.** No retention contract change.
- **Anti-Replication boundary.** Pre-scan is pure-Python regex matching; no LLM, no pricing logic.

---

## §8 — Phase 8 Acceptance Criteria

3A build + 3B review approve when ALL true:

1. **Defect 19 fix verified at Stage 2:** `packages/ingest/excel_extractor.py` contains `_pre_scan_shape_violators` helper, called before `model_validate(body)`, and populates `body["shape_violating_lanes"]`. Static inspection.
2. **Defect 19 fix verified at Stage 4:** `packages/ingest/tasks.py:_validate` reads `shape_violating_lanes` from `normalized`, synthesizes `LaneRecord` instances via `model_construct`, runs `apply_hard_rules` on them, merges results into `validated.deterministically_rejected`. Static inspection.
3. **Defect 20 fix verified:** `extract_excel_payload` wraps `model_validate(body)` in try/except converting `ValidationError` → `ExtractionError`. Static inspection.
4. **`PortCode` schema unchanged:** `packages/core/models/ratesheet.py:51` retains `pattern=r"^[A-Z]{2}[A-Z0-9]{3}$"`. Static inspection.
5. **New schema `ShapeViolatingLane` is REQUIRED-only fields, `extra="forbid"`.** Static inspection.
6. **`NormalizedRatesheet.shape_violating_lanes` field has `default_factory=list`** for backwards compat with V8/V9 historical blobs. Static inspection.
7. **Phase 7 §6.1.1 force-overwrite preserved:** the three force-overwrite lines for `conformal_scores`/`flagged_for_review`/`deterministically_rejected` still present, still direct-assignment. Static inspection.
8. **Phase 7 §6.1.2 prompt unchanged:** the SYSTEM_INSTRUCTIONS shape-violating bullet AND the empty-containers clause still present. Static inspection.
9. **Phase 7 §6.1.3 carve-out preserved (but documented as narrower scope):** `normalizer.py:265-275` block still exists, comments updated to reflect post-Phase-8 reachability. Static inspection.
10. **Test re-architecture verified:**
    - `test_full_pipeline_broken_impossible_port_codes` does NOT use `PortCode.model_construct` in the test body. Submits the real `.xlsx` fixture. Asserts canonical R1 rejection. Verify by reading the test source.
    - `test_stage3_normalizer_passes_shape_violating_ports_to_stage4` is deleted.
    - `test_normalizer_carveout_handles_table_unknown_shape_valid_codes` exists.
    - All mocked tests pass under vanilla `pytest tests/integration -q`.
11. **F.3 happy-path test unchanged** (K+N still passes per V7 evidence; the new pre-scan emits empty collection on K+N, no downstream behavior change). Verify via `git diff` on `test_pipeline_e2e.py`.
12. **`pytest tests/unit -q` passes** baseline (153) plus any net-new unit tests added for `ShapeViolatingLane` validation or `_pre_scan_shape_violators` testing.
13. **`pytest tests/integration -q` passes** the new/rewritten mocked-pipeline tests. F.3/F.4 live-Vertex integration tests do NOT run during 3A/3B; they run during V10.
14. **`ruff check .` clean.**
15. **`ruff format --check .` clean.**
16. **`mypy --strict` clean on changed files.** Pre-existing retention.py/signed_url.py/test_ratesheet_models.py errors remain out-of-scope.
17. **No new secrets in the diff.**
18. **V10 F.4-F.5 readiness.** Phase 8 acceptance does NOT require running V10.

---

## §9 — Explicit NON-GOALS for Phase 8

- **No `PortCode` schema relaxation.** The regex `^[A-Z]{2}[A-Z0-9]{3}$` stays.
- **No new rules in `apply_hard_rules`.** R1..R7 set locked.
- **No `BUILD_COMPLETE_V7.md` written by Phase 8 itself.** That lands after V10 F.4-F.5 actually passes.
- **No retention.py / signed_url.py / test_ratesheet_models.py mypy cleanup.**
- **No K+N fixture regeneration.**
- **No Master PRD or ULTIMATE_PRD prose changes.**
- **No `PHASE_9_SPEC.md`.** Sprint 2 ends at Phase 8 close + V10 F.4-F.5 pass.
- **No new outbox event types.**
- **No deletion of prior closure records, halt records, or spec files.**
- **No backfill of historical `OnrampOutput.normalized_payload` blobs with the new `shape_violating_lanes` field.** Forward-only; the `default_factory=list` handles old blobs cleanly.
- **No re-running of F.3.** F.3 V7 results stand.
- **No changes to `RejectionRecord` schema.** Phase 6.9 shape locked.
- **No changes to the dispatcher's `deliver_audit_log`.** Phase 7 §6.3 contract preserved.
- **No removal of the Phase 7 §6.1.3 normalizer carve-out.** It stays as defense-in-depth, with narrower reachable scope.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_7_SPEC.md`.
- Do NOT modify any `BUILD_COMPLETE*.md` file.
- Do NOT modify any `HUMAN_INTERVENTION_REQUEST*.md` file.
- Do NOT modify `Solvo_Master_PRD.md` or `ULTIMATE_PRD.md`.
- Do NOT modify the F.3 happy-path test or the Defect 6 regression test.
- Do NOT touch R1..R7 precedence or `apply_hard_rules` public signature.
- Do NOT add a new rule.
- Do NOT introduce a new env var.
- Do NOT change `OnrampAuditLog` schema or its migration.
- Do NOT modify the K+N happy-path fixture.
- Do NOT relax `PortCode`'s regex pattern.
- Do NOT remove the Phase 7 §6.1.3 normalizer carve-out (only update its docstring).

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`. The new `ShapeViolatingLane` schema declares this explicitly.
- All Vertex AI calls bind to `location='global'` with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation.
- Container-boot validators fail-fast on misconfiguration.
- Anti-Replication boundary: no pricing, POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing, no rate / margin / recommendation computation.
- **Transactional outbox**: row counts unchanged. The `shape_violating_lanes` data flows through the existing `OnrampOutput.normalized_payload` JSONB column.
- Redis distributed locks use `SET NX EX`.
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus.
- Per-task `make_async_engine` (Phase 6.5) preserved.
- Per-call `get_vertex_client` (Phase 6.6) preserved.
- Deterministic Stage 1 + Stage 4 — zero LLM calls in `classify_format` or in `apply_hard_rules` or any of its R1..R7 branches.
- Phase 7 §11 canonical rule_id literal set — synthetic R1 rejections emitted from re-injected shape-violators have `rule_id="port_unknown_unlocode"`, which is in the canonical set.
- **NEW Phase 8 invariant**: integration tests that purport to exercise a Stage 2 → 3 → 4 contract MUST submit the actual fixture through the real Stage 2 Pydantic gate (no `model_construct` bypass at the test entry point). `model_construct` is permitted only inside production code where the lane is a known sentinel value being routed to R1 for deterministic rejection (Phase 8 §6.1 synthesizes shape-violator LaneRecords this way). Tests that wish to bypass schema validation for setup purposes must be unit tests, not integration tests.

— End of PHASE_8_SPEC.md.
