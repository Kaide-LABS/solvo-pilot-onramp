# PHASE 6.9 SPEC — Fourth and Final Closure Patch

**Output of Step 2 (Phase 6.9 spec generation).** Consumes the Step 4 Stage F.4 halt at commit `7424ae5` (`HUMAN_INTERVENTION_REQUEST_V7.md`), the channel-rename ops commit `265c0e9`, and the BUILD_COMPLETE_V4 closure record at `abaa97d`. Feeds a single Step 3A build cycle, a single Step 3B review cycle, then a V8 Stage F.4-F.5 resume (F.3 does NOT need to re-run). After Phase 6.9 lands and F.4-F.5 passes, Sprint 2 closure is FINAL and demo recording is authorized.

---

## §0 — Phase Plan Header

**This is Phase 6.9 of the Sprint 1 build — a fourth and final closure patch following the Step 4 Stage F.4 halt at commit `7424ae5` (HUMAN_INTERVENTION_REQUEST_V7.md). Phase 6.5 closed Defects 1-3. Phase 6.6 closed Defects 4-7. Direct ops commits (`ace72d6`, `6d3ed3f`, `99453a1`) closed Defects 8-12. Phase 6.8 closed Defects 13-14. Channel-rename ops commit (`265c0e9`) closed Defect 15. Phase 6.9 closes Defects 16 + 17 — the final defects required to make F.4 pass and the deterministic-rejection contract honest. After Phase 6.9 lands and F.4 + F.5 pass (F.3 does NOT need to re-run), Sprint 2 closure is FINAL.**

| Phase | Hour window | Scope |
|---|---|---|
| ✅ Phase 1 – 6 | Sprint 2 build | Scaffolding through Cloud Run deployment. |
| ✅ Phase 6.5 | post-F.3 halt #1 | Defects 1-3 (Celery engine, fixtures, slack_post enqueue). |
| ✅ Phase 6.6 | post-F.3 halt #2 | Defects 4-7 (staging volume, Vertex client cache, failure handler, fixture shrink + budget). |
| ✅ Direct ops (V3+V4) | post-V3 + V4 halts | Defects 8-12 (Dockerfile COPY, storage project arg, IAM-API signing, Slack lru_cache, result-url tx). |
| ✅ Phase 6.8 | post-F.3 halt #3 (V5) | Defects 13-14 + F.3.1 budget re-baseline. |
| ✅ Channel rename | post-F.3 halt #4 (V6) | Defect 15 (`#pilot-onramp` → `#solvo-onramp-demo`). |
| **Phase 6.9** | post-F.4 halt (V7) | **Defects 16 + 17 — F.4 fixture refresh + rejection-record provenance.** |

**Scope:**

- **Defect 16** — F.4 broken fixtures (`broken_impossible_port_codes.xlsx`, `broken_negative_rates.xlsx`, `broken_malformed_edifact.edi`) all carry past validity windows. The deterministic rules engine evaluates R1..R7 in fixed order, and R3 (`validity_window_in_the_past`) fires before R1 (`port_unknown_unlocode`) and R2 (`negative_base_rate`). The named defect each fixture was designed to surface (impossible UN/LOCODE shape, negative rate, malformed EDIFACT) never gets attributed because validity rejects the lane first. Resolution: fixture refresh (move validity windows to future dates), NOT rule re-ordering — Phase 4's R1..R7 precedence is a deliberate semantic ("don't waste compute on stale data") and stays intact.
- **Defect 17** — `RejectionRecord` provenance gap. The current schema (`packages/core/models/ratesheet.py`) is `RejectionRecord(source_row_reference: SourceRow, rule_id: str, rule_description: str)`. All three fields are required-str and the rules engine populates them. But two provenance gaps exist:
  - **(17a)** `RejectionRecord` carries `source_row_reference` (sheet + row + cell coordinates) but NOT the `lane_id` from the originating `LaneRecord`. Master PRD §3.3 promises "deterministically rejected with rule-ID provenance"; F.4 milestone language implies lane-level traceability. Operators reading the Slack summary need to map a rejection back to the lane they care about. Fix: add `lane_id: str` (required) to `RejectionRecord`, populated in `_evaluate_lane` from the input `LaneRecord.lane_id`.
  - **(17b)** `rule_description` is currently a static label from `_RULE_DESCRIPTIONS` — e.g. `"origin or destination port code does not match UN/LOCODE shape"`. It does NOT cite the violating value. The F.4 integration test and the Slack block-kit table both need a value-citing reason — e.g. `"origin port code 'ZZ' is not a valid UN/LOCODE; expected 5-character alphanumeric per UN/LOCODE Code List 2024-2"`. Fix: each branch of `_evaluate_lane` constructs a value-citing `rule_description` string from the lane it's rejecting (the bad port code, the negative number, the past date). The static `_RULE_DESCRIPTIONS` dict stays as the rule-category label but the per-rejection text is per-lane.

**Autonomous-critique adjustment (vs HUMAN_INTERVENTION_REQUEST_V7.md framing):** V7's halt doc described Defect 17 as "rejection records emit null `rejection_reason` and null `lane_id`." The actual schema has neither field — the V7 inspection script keyed `r.get("rejection_reason")` and `r.get("lane_id")` against records whose actual fields are `source_row_reference`, `rule_id`, `rule_description` (all already populated). The OBSERVATION ("null") was a key-mismatch artifact in the smoke script, not a population bug. The REAL gap is the two provenance shortfalls above (17a + 17b). Phase 6.9 fixes the real gaps; the V7 prompt's literal "rejection_reason / lane_id" naming maps to (17b/17a) in this spec. The V8 smoke script must update its key references from `rejection_reason`/`lane_id` to `rule_description`/`lane_id` to verify Phase 6.9's outcome correctly.

---

## §0.5 — Citation Re-Verification Gate

**Status: N/A for Phase 6.9.** Per ULTIMATE_PRD §4.7, provisional citations were re-verified at the Phase 2 and Phase 4 boundaries. Phase 6.9 introduces no new academic claims — it is pure fixture + provenance work.

---

## §1 — Files Added or Modified

**Modified:**

- `fixtures/broken_impossible_port_codes.xlsx` — **MODIFIED**. Validity-window cells future-dated (`validity_start=2026-06-01`, `validity_end=2026-12-31`). The impossible UN/LOCODE entries (the named defect) remain untouched.
- `fixtures/broken_negative_rates.xlsx` — **MODIFIED**. Same validity-window refresh. Negative rate (the named defect) untouched.
- `fixtures/broken_malformed_edifact.edi` — **MODIFIED** (conditional). EDIFACT validity is encoded in DTM segments (qualifier 36 = end-of-validity per UN/EDIFACT D.96A). The build agent grep-locates the DTM+36 segment and rewrites its ISO 8601 date to a future date. The structural malformation (the named defect — missing/inverted UNH/UNT or broken delimiter) remains untouched. If the file's actual rejection mechanism is at the classifier (file fails to parse before reaching Stage 4), the agent inspects the V7 attempt's job_id `d4983b60741943ddb64bb341c7bbc264` outbox + audit-log via `MSYS_NO_PATHCONV=1 docker compose exec postgres psql ...` and reports the actual rejection pathway. The fix moves accordingly:
  - If R3 fires inside Stage 4: future-date the DTM+36 segment.
  - If extraction fails and synthesizes a rejection: the fix lives in the extractor's failure-shape, not the fixture.
- `packages/core/models/ratesheet.py` — **MODIFIED**. Add `lane_id: str = Field(min_length=1, max_length=64)` to `RejectionRecord`. New REQUIRED field. No default, no `Optional`. Keep `model_config = ConfigDict(extra="forbid")`. Backwards-compat note: the `OnrampOutput.normalized_payload` JSONB column will start carrying `lane_id` keys in newly written records. Old records (V7 attempt and earlier) lack the key; the schema's `extra="forbid"` policy applies only on input validation, not on dict serialization, so old archived blobs do not break — but reading them back via `NormalizedRatesheet.model_validate(...)` will fail. Phase 6.9 acceptance does NOT require backfilling old blobs (Sprint 2 demo only needs forward correctness); a follow-on cleanup (post-engagement) can backfill if needed.
- `packages/ingest/rules_engine.py` — **MODIFIED**. `_evaluate_lane` returns a value-citing `RuleViolation` shape (or the rules engine's emit-side patch builds the `RejectionRecord` directly with both value-citing `rule_description` and `lane_id` from `lane.lane_id`). Patch in `apply_hard_rules` where the `RejectionRecord(...)` is constructed: pass `lane_id=lane.lane_id` AND replace the static `rule_description` with the per-rule value-citing string. Implementation logic in §6.2 below.
- `packages/core/models/conformal.py` — **VERIFY ONLY** (no change expected). `RuleViolation` schema is the in-flight emit type returned by `_evaluate_lane`. The agent inspects its current fields and either: (a) keeps `RuleViolation` as-is and constructs the value-citing `rule_description` inside `apply_hard_rules` (cleaner; preserves `_evaluate_lane` signature), OR (b) extends `RuleViolation` to carry the value-citing description through. Either is acceptable; (a) is the smaller diff.
- `tests/unit/test_rules_engine.py` — **MODIFIED** (or **NEW** if doesn't exist; the agent confirms via Nia). Add one unit test per rule branch (R1..R7) asserting:
  - `rule_id` matches the expected literal
  - `lane_id` matches the input `LaneRecord.lane_id`
  - `rule_description` is non-empty AND contains a representation of the violating value (the bad port code, the negative number formatted as a string, the past date as ISO).
- `tests/integration/test_pipeline_e2e.py` — **MODIFIED**. Add three new test functions (do NOT modify the F.3 happy-path test `test_kn_15_lane_reaches_completed_and_emits_slack_post` or the Defect 6 regression test `test_normalize_failure_surfaces_as_status_failed`):
  - `test_broken_impossible_port_codes_rejects_with_port_unknown_unlocode`
  - `test_broken_negative_rates_rejects_with_negative_base_rate`
  - `test_broken_malformed_edifact_rejects_with_structural_citation`

  Each test: submits the corresponding fixture, polls to completion, fetches the signed URL with 3 × 2s retry (Phase 6.8 §6.2.1 race), parses the result JSON, asserts the FIRST entry in `deterministically_rejected` has the expected `rule_id` AND every entry has non-null `lane_id` AND non-empty `rule_description` containing a value-citing substring.

**Added:** none (new tests live in existing test files; no new modules).

**Deleted:** none. HUMAN_INTERVENTION_REQUEST_V3 through V7, BUILD_COMPLETE through V4, and all prior PHASE_*_SPEC.md files remain on disk as the historical record.

---

## §2 — Pip Dependencies

**None.** Phase 6.9 is pure logic + fixture work. No new deps. The fixture refresh uses the already-installed `openpyxl` for the .xlsx files; the .edi file is plain text and uses no library.

---

## §3 — Pydantic Schemas

**One schema change** — `RejectionRecord` in `packages/core/models/ratesheet.py`:

```python
class RejectionRecord(BaseModel):
    """Hard-rejected row with deterministic rule citation."""

    model_config = ConfigDict(extra="forbid")

    source_row_reference: SourceRow
    lane_id: str = Field(min_length=1, max_length=64)   # NEW (Phase 6.9 §3)
    rule_id: str = Field(min_length=1, max_length=64)
    rule_description: str = Field(min_length=1, max_length=256)
```

The `lane_id` field is REQUIRED, not Optional. The originating `LaneRecord.lane_id` always exists (Phase 2 contract), so the rules engine can always supply it.

`source_row_reference` stays — it carries the spreadsheet-level provenance the audit-log needs. `lane_id` adds the lane-level provenance the Slack summary needs. They are complementary, not redundant.

---

## §4 — FastAPI Route Signatures

**No route changes.**

---

## §5 — Alembic Migration

**No migration.** `OnrampOutput.normalized_payload` is a JSONB column; the new `lane_id` field nests inside the JSON value and is not visible to the DB schema.

---

## §6 — Implementation Logic Flow

### §6.1 — Defect 16 Fix: Fixture Refresh

For each broken xlsx fixture, the build agent uses `openpyxl` to:

1. Open the workbook.
2. Locate the validity-window cells. The Phase 6.6 fixture-generation patch (§6.4.1) is the authoritative source for fixture structure; the V7 attempt's first-evaluated rule on each fixture was R3 (`validity_window_in_the_past`), confirming the dates live in a place the rules engine reads via `LaneRecord.validity_end`. The agent grep-locates "valid" / "validity" cells or inspects the workbook's `extract_excel_payload` output to find which cell becomes `validity_end` per lane.
3. Rewrite each `validity_start` to `2026-06-01` and each `validity_end` to `2026-12-31`. (Both dates are inside Phase 6.6's existing demo window and are future-dated relative to today's 2026-05-26.)
4. Save in-place.

#### §6.1.1 — Determinism contract preservation

Phase 6.6 §6.4.1 specified a determinism contract for the fixtures (dcterms:modified rewrite + sorted zip members) so their content-hash is reproducible across rebuilds. The agent applies the same determinism patches to the modified fixtures so the input_hash is stable. If the Phase 6.6 generation script lives at `scripts/generate_kn_fixture.py` (or similar — agent finds via Nia), the broken fixtures can be regenerated through the same path with future-dated validity rather than touched in-place. Either approach is acceptable; in-place edit is the smaller diff.

#### §6.1.2 — broken_impossible_port_codes.xlsx

The "impossible UN/LOCODE" defect is shape-violating port codes (e.g. lowercase, too short, non-alphanumeric). The PortCode model's `pattern=r"^[A-Z]{2}[A-Z0-9]{3}$"` is the enforcing regex; the rules-engine R1 re-checks the same regex as defense-in-depth. Once validity windows move to the future, R1 fires first on lanes with bad-shape ports → `rule_id="port_unknown_unlocode"` is correctly attributed.

If the fixture's port codes are all VALID-shape but absent from `un_locode_reference` (table-membership defect, not shape defect), then R1 does NOT catch them — Stage 3 normalization is supposed to resolve them and Phase 4's R1 only checks SHAPE. In that case, the fixture either needs port codes refreshed to bad SHAPE (so R1 catches them as the named defect) OR a new R8 (`port_not_in_unlocode_table`) is added. Phase 6.9's NON-GOAL list forbids new rules; the agent therefore refreshes the fixture's port codes to bad-shape values that R1 will catch (e.g., `"zz"`, `"USXX1"` then mangle to `"USX@1"`, etc.). The agent confirms via openpyxl read that the current fixture's port codes are bad-shape; if they are, no further port-code changes are needed.

#### §6.1.3 — broken_negative_rates.xlsx

Negative or zero `base_rate_usd` is R2 (`negative_base_rate`). Once validity is future-dated, R2 fires correctly. No rate changes needed.

#### §6.1.4 — broken_malformed_edifact.edi

EDIFACT plain-text. The V7 attempt showed this fixture surface 1 rejection with `rule_id="validity_window_in_the_past"`, which strongly suggests the extractor DID successfully parse at least one lane out of the malformed file (otherwise the rules engine would not see any LaneRecord). The agent:

1. Reads the .edi file via Nia.
2. Locates `DTM+36:<date>:102` (qualifier 36 = end-of-validity, 102 = CCYYMMDD format).
3. Rewrites the date to `20261231`.
4. Saves.

If the file does NOT contain a DTM+36 segment, then the validity_end came from a default elsewhere in the extractor — the agent reports the actual source and Phase 6.9 §6.1.4 reframes to "extraction-fallback default future-dated."

The named structural malformation (missing UNH segment, broken UNT count, etc.) remains.

### §6.2 — Defect 17 Fix: Rejection-Record Provenance

Current code in `packages/ingest/rules_engine.py`:

```python
def _evaluate_lane(lane: LaneRecord, today: datetime) -> RuleViolation | None:
    if not (
        _UNLOCODE_SHAPE.match(lane.origin_port.code)
        and _UNLOCODE_SHAPE.match(lane.destination_port.code)
    ):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=_RULE_DESCRIPTIONS["port_unknown_unlocode"],
        )
    ...
```

And the `apply_hard_rules` emit-side:

```python
rejected.append(
    RejectionRecord(
        source_row_reference=lane.source_row_reference,
        rule_id=violation.rule_id,
        rule_description=violation.rule_description,
    )
)
```

Patched shape (Path (a) from §1 — preserve `_evaluate_lane`'s signature, build the value-citing description + lane_id at emit time inside `apply_hard_rules`):

The build agent extends `_evaluate_lane` to return a value-citing `rule_description` directly. Each branch composes its own description string from the lane:

```python
def _evaluate_lane(lane: LaneRecord, today: datetime) -> RuleViolation | None:
    if not _UNLOCODE_SHAPE.match(lane.origin_port.code):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=(
                f"origin port code {lane.origin_port.code!r} does not match the "
                f"UN/LOCODE shape ^[A-Z]{{2}}[A-Z0-9]{{3}}$"
            ),
        )
    if not _UNLOCODE_SHAPE.match(lane.destination_port.code):
        return RuleViolation(
            rule_id="port_unknown_unlocode",
            rule_description=(
                f"destination port code {lane.destination_port.code!r} does not "
                f"match the UN/LOCODE shape ^[A-Z]{{2}}[A-Z0-9]{{3}}$"
            ),
        )
    if lane.base_rate_usd <= Decimal("0"):
        return RuleViolation(
            rule_id="negative_base_rate",
            rule_description=(
                f"base_rate_usd={lane.base_rate_usd} is zero or negative; "
                f"R2 requires a strictly positive USD amount"
            ),
        )
    if lane.validity_end < today.date():
        return RuleViolation(
            rule_id="validity_window_in_the_past",
            rule_description=(
                f"validity_end={lane.validity_end.isoformat()} is before "
                f"today ({today.date().isoformat()} UTC); rate is stale"
            ),
        )
    if lane.validity_start > lane.validity_end:
        return RuleViolation(
            rule_id="validity_window_inverted",
            rule_description=(
                f"validity_start={lane.validity_start.isoformat()} is after "
                f"validity_end={lane.validity_end.isoformat()}"
            ),
        )
    if lane.transit_time_days is not None and not 1 <= lane.transit_time_days <= 120:
        return RuleViolation(
            rule_id="transit_time_out_of_range",
            rule_description=(
                f"transit_time_days={lane.transit_time_days} falls outside the "
                f"[1, 120] envelope"
            ),
        )
    if lane.equipment_type not in _EQUIPMENT_TYPES:
        return RuleViolation(
            rule_id="equipment_type_unknown",
            rule_description=(
                f"equipment_type={lane.equipment_type!r} is not in the locked "
                f"Literal set {sorted(_EQUIPMENT_TYPES)}"
            ),
        )
    for surcharge in lane.surcharges:
        if surcharge.applies_per not in _SURCHARGE_BASES:
            return RuleViolation(
                rule_id="surcharge_basis_unknown",
                rule_description=(
                    f"surcharge {surcharge.code!r}.applies_per="
                    f"{surcharge.applies_per!r} not in locked Literal set "
                    f"{sorted(_SURCHARGE_BASES)}"
                ),
            )
    return None
```

The `_RULE_DESCRIPTIONS` dict stays as the rule-category label table (used by audit-log emission and potentially by the Block Kit summary's group-by-rule rendering). It is now a documentation aide rather than the primary source of rejection text.

In `apply_hard_rules`, the emit-side picks up `lane_id`:

```python
for lane in rs.lanes:
    violation = _evaluate_lane(lane, today)
    if violation is None:
        surviving.append(lane)
        continue
    rejected.append(
        RejectionRecord(
            source_row_reference=lane.source_row_reference,
            lane_id=lane.lane_id,                              # NEW (Phase 6.9 §6.2)
            rule_id=violation.rule_id,
            rule_description=violation.rule_description,
        )
    )
    violations.append(violation)
```

**Invariants preserved:**

- Zero LLM calls (Stage 4 deterministic).
- Anti-Replication: no pricing, no monetary derivation. The value-citing strings include the bad rate as a debugging artifact, NOT as a recommendation.
- Rule precedence R1..R7 unchanged.
- `apply_hard_rules` public signature unchanged.
- `_RULE_DESCRIPTIONS` dict retained.

### §6.3 — Unit Test Coverage

Add `tests/unit/test_rules_engine.py` (or extend if it exists):

```python
"""Stage 4 rules engine unit tests. PHASE_4_SPEC §6.1 + PHASE_6_9_SPEC §6.3."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.core.models.ratesheet import (
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
    SurchargeRecord,
    ExtractionMetadata,
)
from packages.ingest.rules_engine import apply_hard_rules

_NOW = datetime(2026, 5, 26, 0, 0, 0, tzinfo=UTC)


def _baseline_lane(**overrides) -> LaneRecord:
    base = dict(
        lane_id="LANE_TEST_001",
        origin_port=PortCode(code="USNYC"),
        destination_port=PortCode(code="NLRTM"),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal("2500.00"),
        surcharges=[],
        transit_time_days=14,
        validity_start=date(2026, 6, 1),
        validity_end=date(2026, 12, 31),
        source_row_reference=SourceRow(sheet_name="Sheet1", row_number=2, cell_reference="A2"),
    )
    base.update(overrides)
    return LaneRecord(**base)


def _wrap(lane: LaneRecord) -> NormalizedRatesheet:
    return NormalizedRatesheet(
        job_id="job_test_001",
        prospect_id="test-prospect",
        extraction_metadata=ExtractionMetadata(
            extractor_model="gemini-3.1-flash-lite",
            extracted_at=_NOW,
            prompt_version="phase4.v1",
            cell_count=10,
        ),
        lanes=[lane],
    )


def test_r1_port_unlocode_emits_full_record() -> None:
    # PortCode itself enforces the shape regex, so we route the bad code
    # through the model_construct backdoor used elsewhere in defense-in-depth
    # tests — OR test against the rules-engine layer with a hand-built lane.
    lane = _baseline_lane()
    bad = lane.model_copy(update={"origin_port": PortCode.model_construct(code="zz")})
    rs, violations = apply_hard_rules(_wrap(bad), now=_NOW)
    assert len(rs.deterministically_rejected) == 1
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "port_unknown_unlocode"
    assert rej.lane_id == "LANE_TEST_001"
    assert "zz" in rej.rule_description
    assert "UN/LOCODE" in rej.rule_description


def test_r2_negative_rate_emits_full_record() -> None:
    lane = _baseline_lane(base_rate_usd=Decimal("-100"))
    rs, _ = apply_hard_rules(_wrap(lane), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "negative_base_rate"
    assert rej.lane_id == "LANE_TEST_001"
    assert "-100" in rej.rule_description


def test_r3_validity_past_emits_full_record() -> None:
    lane = _baseline_lane(
        validity_start=date(2025, 1, 1), validity_end=date(2025, 12, 31)
    )
    rs, _ = apply_hard_rules(_wrap(lane), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "validity_window_in_the_past"
    assert rej.lane_id == "LANE_TEST_001"
    assert "2025-12-31" in rej.rule_description


def test_r4_validity_inverted_emits_full_record() -> None:
    lane = _baseline_lane(
        validity_start=date(2026, 12, 31), validity_end=date(2026, 6, 1)
    )
    rs, _ = apply_hard_rules(_wrap(lane), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "validity_window_inverted"
    assert rej.lane_id == "LANE_TEST_001"
    assert "2026-06-01" in rej.rule_description and "2026-12-31" in rej.rule_description


def test_r5_transit_out_of_range_emits_full_record() -> None:
    lane = _baseline_lane(transit_time_days=None)
    lane = lane.model_copy(update={"transit_time_days": 200})  # bypass Pydantic le=120
    # If model_copy preserves the ge/le constraint via re-validation, route
    # through model_construct for the bypass. Build agent picks the right
    # bypass.
    rs, _ = apply_hard_rules(_wrap(lane), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "transit_time_out_of_range"
    assert "200" in rej.rule_description


def test_r6_equipment_type_unknown_emits_full_record() -> None:
    lane = _baseline_lane()
    bad = lane.model_copy(update={"equipment_type": "BOGUS_RIG"})
    rs, _ = apply_hard_rules(_wrap(bad), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "equipment_type_unknown"
    assert "BOGUS_RIG" in rej.rule_description


def test_r7_surcharge_basis_unknown_emits_full_record() -> None:
    lane = _baseline_lane(
        surcharges=[
            SurchargeRecord.model_construct(
                code="BAF", amount_usd=Decimal("50.00"), applies_per="WEEK"
            )
        ]
    )
    rs, _ = apply_hard_rules(_wrap(lane), now=_NOW)
    rej = rs.deterministically_rejected[0]
    assert rej.rule_id == "surcharge_basis_unknown"
    assert "BAF" in rej.rule_description and "WEEK" in rej.rule_description
```

The build agent confirms via Nia whether `tests/unit/test_rules_engine.py` already exists and merges accordingly. If it exists, append the new tests; if not, create the file with the test scaffolding above. Pydantic-bypass mechanisms (`model_construct` vs `model_copy`) depend on whether Phase 2's models re-validate on `model_copy` — the agent picks the right bypass per branch.

### §6.4 — Integration Test Coverage

Add three new tests in `tests/integration/test_pipeline_e2e.py`, immediately after the existing `test_kn_15_lane_reaches_completed_and_emits_slack_post`. Do NOT modify the existing test.

Sketch — the build agent picks the precise shape against the actual test fixtures + adapts to the prior `_submit_job` / `_poll_until_completed` helpers:

```python
@pytest.mark.asyncio
async def test_broken_impossible_port_codes_rejects_with_port_unknown_unlocode(
    _compose_stack_ready: None,
) -> None:
    """Phase 6.9 §6.4: F.4 fixture with bad-shape UN/LOCODEs must reject via R1."""
    # Submit the fixture (the broken_impossible_port_codes.xlsx with the
    # Phase 6.9 §6.1.2 validity refresh applied).
    job_id = _submit_broken_fixture("broken_impossible_port_codes.xlsx", "C-E2E-F4")
    final_status = _poll_until_completed(job_id)
    assert final_status == "completed"

    # Fetch signed URL + GET with retry (Phase 6.8 §6.2.1 race).
    result = await _fetch_signed_blob(job_id)

    rejected = result["deterministically_rejected"]
    assert len(rejected) >= 1
    first = rejected[0]
    assert first["rule_id"] == "port_unknown_unlocode", (
        f"expected R1 to fire first; got {first['rule_id']} — Defect 16 regression"
    )
    for r in rejected:
        assert r.get("lane_id"), "Defect 17a regression: lane_id missing"
        assert r.get("rule_description"), "Defect 17b regression: rule_description missing"


@pytest.mark.asyncio
async def test_broken_negative_rates_rejects_with_negative_base_rate(
    _compose_stack_ready: None,
) -> None:
    """Phase 6.9 §6.4: F.4 fixture with negative base_rate_usd must reject via R2."""
    job_id = _submit_broken_fixture("broken_negative_rates.xlsx", "C-E2E-F4")
    final_status = _poll_until_completed(job_id)
    assert final_status == "completed"
    result = await _fetch_signed_blob(job_id)
    rejected = result["deterministically_rejected"]
    assert any(r["rule_id"] == "negative_base_rate" for r in rejected), (
        f"expected at least one negative_base_rate rejection; got "
        f"{[r['rule_id'] for r in rejected]}"
    )
    for r in rejected:
        assert r.get("lane_id"), "Defect 17a regression: lane_id missing"
        assert r.get("rule_description"), "Defect 17b regression: rule_description missing"


@pytest.mark.asyncio
async def test_broken_malformed_edifact_rejects_with_structural_citation(
    _compose_stack_ready: None,
) -> None:
    """Phase 6.9 §6.4: malformed EDIFACT must reject at extraction OR with a structural rule citation."""
    job_id = _submit_broken_fixture("broken_malformed_edifact.edi", "C-E2E-F4")
    final_status = _poll_until_completed(job_id)
    # Acceptable outcomes: completed-with-rejections OR failed-at-extraction.
    assert final_status in {"completed", "failed"}
    if final_status == "completed":
        result = await _fetch_signed_blob(job_id)
        rejected = result["deterministically_rejected"]
        for r in rejected:
            assert r.get("lane_id"), "Defect 17a regression: lane_id missing"
            assert r.get("rule_description"), "Defect 17b regression: rule_description missing"
        # The rule_id should NOT be validity_window_in_the_past after fixture refresh.
        assert all(r["rule_id"] != "validity_window_in_the_past" for r in rejected), (
            "Defect 16 regression: validity_window still masking EDIFACT structural defect"
        )
```

The build agent adds the helpers (`_submit_broken_fixture`, `_fetch_signed_blob`) if they don't already exist in the file, factoring the inline submit + poll + signed-URL fetch from the existing happy-path test. Helpers are private (underscore prefix) and live in the same test module.

These integration tests do NOT run during 3A/3B (they need the live compose stack and burn Vertex quota). They run during V8 F.4 resume. Phase 6.9 acceptance only requires the test code to be present and syntactically valid (caught by `ruff check` + `mypy --strict`).

---

## §7 — Cross-Phase Integration Requirements

Phase 6.9 must NOT break:

- **Phase 6.5 per-task `make_async_engine`.** Phase 6.9 does not touch task wiring.
- **Phase 6.6 per-call `get_vertex_client`.** Orthogonal — Phase 6.9 is pure deterministic Stage 4 work.
- **Phase 6.6 `_failure_payload` / `_commit_failure`.** Untouched.
- **Phase 6.8 4-row success-path transaction** (audit_log/validated + slack_post + upload_result + OnrampOutput upsert). Untouched. The new `lane_id` field on `RejectionRecord` lands inside `OnrampOutput.normalized_payload`'s `deterministically_rejected` array — same column, same commit.
- **Stage 4 R1..R7 precedence.** Phase 4's deterministic ordering preserved verbatim.
- **`RejectionRecord` `extra="forbid"`.** New field is part of the schema, not "extra."
- **The F.3 happy-path test.** Do NOT modify it. The new `lane_id` field will appear in any rejection record the happy-path produces (the K+N fixture produces 1 rejection per run); the happy-path test doesn't inspect the rejection record's shape today so adding a field is non-regressive.
- **The Defect 6 regression test.** Untouched.
- **§3.10 retention posture.** Vertex calls still route via `location='global'`. Cloud Run + GCS stay europe-west4. Models pinned. Zero-retention.
- **Anti-Replication boundary.** No pricing, no POMDP, no RL, no market-clearing.
- **Redis distributed lock pattern.** `SET NX EX` unchanged.
- **N=3 ensemble at (0.1, 0.5, 0.9), majority-vote consensus, per-lane parallelism.** Untouched.

---

## §8 — Phase 6.9 Acceptance Criteria

3A build + 3B review approve when ALL true:

1. **Three broken fixtures have future-dated validity windows.** Verify by:
   - `python -c "import openpyxl; wb=openpyxl.load_workbook('fixtures/broken_impossible_port_codes.xlsx'); ..."` extracting the validity_end cells and asserting all are ≥ 2026-06-01.
   - Same for `broken_negative_rates.xlsx`.
   - For `broken_malformed_edifact.edi`: `grep "DTM+36"` returns a future-dated segment, OR the agent's investigation in §6.1.4 confirmed the file's validity defaults are not in the file itself.
2. **`RejectionRecord` schema has new `lane_id: str` REQUIRED field.** Static inspection of `packages/core/models/ratesheet.py`. No default, no Optional.
3. **`packages/ingest/rules_engine.py` `_evaluate_lane` returns value-citing `rule_description`.** Every R1..R7 branch composes the description from the lane's actual values (the bad port code, the negative number, the past date, etc.). Static inspection.
4. **`apply_hard_rules` emits `RejectionRecord(... lane_id=lane.lane_id, ...)`.** Static inspection.
5. **New unit tests in `tests/unit/test_rules_engine.py` — one per rule R1..R7.** All pass under `pytest tests/unit -q`.
6. **New integration tests in `tests/integration/test_pipeline_e2e.py` — three new tests.** Test code is syntactically valid (ruff + mypy clean); the tests themselves do not run during 3A/3B.
7. **F.3 happy-path test in `tests/integration/test_pipeline_e2e.py` is unmodified.** `git diff` shows no changes to `test_kn_15_lane_reaches_completed_and_emits_slack_post` or to `test_normalize_failure_surfaces_as_status_failed`.
8. **`pytest tests/unit -q` passes baseline + new tests.** Expect 148 (prior baseline) + 7 (R1..R7 unit tests) = 155+ passing.
9. **`ruff check .` clean.**
10. **`ruff format --check .` clean.**
11. **`mypy --strict` clean on changed files** (`packages/core/models/ratesheet.py packages/ingest/rules_engine.py tests/unit/test_rules_engine.py tests/integration/test_pipeline_e2e.py`). The 6 pre-existing `packages/compliance/retention.py` errors + 1 `packages/storage/signed_url.py` error remain out-of-scope per PHASE_6_6 §9 + PHASE_6_8 critique.
12. **No new secrets in the diff.** `gitleaks detect --no-banner --no-git --source .` zero findings (or visual inspection if gitleaks not available).
13. **Stage F.4-F.5 resume readiness.** Post-approval validation. Phase 6.9 acceptance does NOT require running F.4-F.5; that's the V8 gate. F.3 also does not need to re-run — its V7 results stand.

---

## §9 — Explicit NON-GOALS for Phase 6.9

- **No `BUILD_COMPLETE_V5.md` written by Phase 6.9 itself.** That lands after F.4-F.5 actually passes against the Phase 6.9 stack.
- **No rule precedence changes.** R1..R7 ordering preserved exactly.
- **No new rules added.** Phase 4's set of 7 rules is the locked surface.
- **No retention.py mypy cleanup.** Still out of scope.
- **No signed_url.py mypy cleanup.** Still out of scope.
- **No F.3 happy-path test modifications.**
- **No Defect 6 regression test modifications.**
- **No fixture regeneration of `K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx`.** Only the three broken fixtures touch.
- **No Master PRD §3.3 narrative changes.** The "deterministically rejected with rule-ID provenance" claim is correct in intent — Phase 6.9 makes the artifact match.
- **No `_recover_requested_slack_channel` refactor.**
- **No `PHASE_7_SPEC.md`.** Sprint 2 ends at Phase 6.9 close + F.4-F.5 pass.
- **No new outbox event types.**
- **No deletion of prior closure or halt records.**
- **No re-running of F.3.** Phase 6.9 acceptance + V8 resume are F.4-only and F.5-only.
- **No backfill of old `OnrampOutput.normalized_payload` blobs with the new `lane_id` field.** Forward correctness only; old V7 attempt blobs lacking `lane_id` are tolerated.
- **No change to `RuleViolation` schema** (in `packages/core/models/conformal.py`) — the in-flight emit type. The value-citing description is constructed inside `_evaluate_lane`'s existing return path.

---

## §10 — Critical Boundaries for the 3A Build Agent

- Do NOT touch `PHASE_1_SPEC.md` through `PHASE_6_SPEC.md`, or `PHASE_6_5_SPEC.md`, `PHASE_6_6_SPEC.md`, `PHASE_6_8_SPEC.md`.
- Do NOT modify any `BUILD_COMPLETE*.md` file.
- Do NOT modify any `HUMAN_INTERVENTION_REQUEST*.md` file.
- Do NOT modify `Solvo_Master_PRD.md` or `ULTIMATE_PRD.md`.
- Do NOT modify the F.3 happy-path test (`test_kn_15_lane_reaches_completed_and_emits_slack_post`) or the Defect 6 regression test (`test_normalize_failure_surfaces_as_status_failed`).
- Do NOT touch R1..R7 precedence or the `apply_hard_rules` public signature.
- Do NOT add a new rule.
- Do NOT introduce a new env var.
- Do NOT add inner retry logic.
- Do NOT change `OnrampOutput.normalized_payload`'s column type or shape — only the JSON schema serialized into it changes.
- Do NOT modify the K+N happy-path fixture.

---

## §11 — Hard Invariants (Restated)

- Every Pydantic `BaseModel` uses `model_config = ConfigDict(extra="forbid")`.
- All Vertex AI calls bind to `location='global'` (Path-1 routing) with Cloud Run + storage in europe-west4.
- Model strings exactly as pinned: `gemini-3.1-flash-lite` (Stage 2), `gemini-3.1-pro-preview` (Stage 3).
- Zero-retention configuration on every Vertex AI client invocation.
- Container-boot validators fail-fast on misconfiguration.
- Anti-Replication boundary: no pricing, POMDP / Bayesian RL / Constrained MDP / value iteration, no market-clearing, no rate / margin / recommendation computation. The value-citing `rule_description` strings include the bad rate as a rejection-diagnostic artifact, NOT as a price recommendation.
- **Transactional outbox**: success-path 3 outbox rows + the OnrampOutput upsert + the status='completed' update in one transaction (audit_log/validated + slack_post + upload_result). Failure-path outbox rows commit in a separate transaction.
- Redis distributed locks use `SET NX EX`.
- N=3 Pro ensemble at temperatures (0.1, 0.5, 0.9) with majority-vote consensus stays exactly as Phase 3 shipped.
- Per-task `make_async_engine` (Phase 6.5) preserved across `_classify`, `_extract`, `_normalize`, `_validate`, `_drain_once`, `archive_completed_jobs`, AND `deliver_upload_result`.
- Per-call `get_vertex_client` (Phase 6.6) preserved.
- Deterministic Stage 1 + Stage 4 — zero LLM calls in `classify_format` or in `apply_hard_rules` or any of its R1..R7 branches.

— End of PHASE_6_9_SPEC.md.
