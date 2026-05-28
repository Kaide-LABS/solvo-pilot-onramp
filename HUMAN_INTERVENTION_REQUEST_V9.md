# HUMAN INTERVENTION REQUEST — V9

**Run:** Step 4 V9 (post-Phase-7 closure)
**HEAD at halt:** `378323b` (BUILD_COMPLETE_V6.md)
**Phase 7 implementation:** `4a1a257`
**Phase 7 approval:** `00f84dc`
**Halt scope:** F.4 partial (1 fail, 2 pass), F.5 NOT RUN
**Vertex spend this run:** ≈$0.10 (3 jobs, dominated by 1 BPC retry path before failure surfaced)

## Pre-flight result

- All Phase 7 artifact greps verified on disk.
- `docker compose down -v && build && up --wait` clean.
- `/v1/health`: all 4 validators PASS (`vertex_ai_handshake`, `postgres_alembic_head`, `un_locode_table_integrity`, `vertex_ai_compliance_handshake`).
- Fixtures staged.

## F.4 results

| Fixture | Status | Latency | Verdict | Notes |
|---|---|---|---|---|
| `broken_impossible_port_codes.xlsx` | stuck at `extracting` | timeout @ 261s | **✗ FAIL** | Defect 19 + Defect 20 (see below) |
| `broken_negative_rates.xlsx` | `completed` | 51s | **✓ PASS** | `rule_id=negative_base_rate`, 1 rejection, lane_id + rule_description present (host-side Python `cp1252` console UnicodeEncodeError on `✓` is a console-printer artifact, not a stack defect) |
| `broken_malformed_edifact.edi` | `completed` | 12s | **✓ PASS** | 0 rejections, 0 `validity_window_in_the_past` hits → spec allows this; Phase 7 §6.2 18b verified live (DTM+36:20261231 future-dated overrides Flash's hallucinated past validity_end) |

## F.5 results

NOT RUN — halt before F.5 because F.4 BPC failed.

## Defect 19 — Phase 7 §6.1 contract broken by Stage 2 PortCode schema regex

**Severity:** Critical. Phase 7 §6.1.3 Stage 3 normalizer carve-out is dead code in the live stack.

### Symptom

`broken_impossible_port_codes.xlsx` upload → Stage 1 classify succeeds → Stage 2 `extract_payload_task` raises `pydantic.ValidationError` and the job sticks at status=`extracting` indefinitely. Worker log:

```
ERROR/ForkPoolWorker-4 Task tasks.ingest.extract_payload[…] raised unexpected:
  2 validation errors for NormalizedRatesheet
  lanes.2.origin_port.code
    String should match pattern '^[A-Z]{2}[A-Z0-9]{3}$' [type=string_pattern_mismatch, input_value='ZZ@ZZ', input_type=str]
  lanes.4.destination_port.code
    String should match pattern '^[A-Z]{2}[A-Z0-9]{3}$' [type=string_pattern_mismatch, input_value='QQ@QQ', input_type=str]
  File "/app/packages/ingest/tasks.py", line 237, in _extract
    payload, _meta = await extract_excel_payload(...)
```

### Root cause

`packages/core/models/ratesheet.py:51`:

```python
class PortCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$", min_length=5, max_length=5)
```

Phase 7 §6.1.2 (`prompts.py` SYSTEM_INSTRUCTIONS) tells the LLM that shape-violating port codes "MUST be included in `lanes` with the port code passed through unchanged." But at the end of `extract_excel_payload` (`excel_extractor.py:205`), `NormalizedRatesheet.model_validate(body)` rejects the constructed body because `PortCode.code` enforces the canonical UN/LOCODE regex. Stage 2's Pydantic gate fires BEFORE Stage 3's §6.1.3 carve-out can run. The carve-out at `normalizer.py:265-275` is therefore unreachable in production.

### Why the Phase 7 mocked test missed this

`tests/integration/test_stage_pipeline_mocked.py:64-69` — `_lane(...)` explicitly bypasses Pydantic validation:

```python
# Use model_construct on PortCode so we can simulate the post-18a contract
# where Stage 2 passes shape-violating codes through into `lanes`.
return LaneRecord(
    lane_id=lane_id,
    origin_port=PortCode.model_construct(code=origin_code),
    destination_port=PortCode.model_construct(code=destination_code),
    ...
)
```

The comment acknowledges the schema collision but works around it instead of resolving it. The mocked test exercises a contract the live stack cannot honour.

### Design-judgment options (all touch invariants)

Each option needs an architecture decision; do not choose ad-hoc:

- **A — Relax `PortCode` regex.** Drop `pattern=` from `PortCode.code` (and possibly `min_length/max_length`). Stage 4 R1 `port_unknown_unlocode` becomes the sole shape gate. Pros: matches Phase 7 §6.1's intent; carve-out becomes reachable. Cons: weakens `PortCode` as a "white-box anchor" (per the model docstring referencing ULTIMATE_PRD §3 hard invariant); every other consumer of `PortCode` must tolerate unconstrained strings; the Phase 2 invariant comment in `ratesheet.py:1-6` requires updating.
- **B — Introduce `RawPortCode` permissive type at Stage 2 only.** Stage 2 uses a new `RawPortCode(BaseModel)` with `code: str = Field(min_length=1, max_length=16)`; Stage 3 converts to canonical `PortCode` after `resolve_port_code` succeeds, or leaves as `RawPortCode` if `_UNLOCODE_SHAPE.match(...)` fails (Stage 4 R1 reads `.code` polymorphically). Pros: preserves canonical `PortCode` strict invariant downstream; cleanest separation. Cons: type-system churn — `LaneRecord.origin_port` must become `PortCode | RawPortCode`; `apply_hard_rules` and all consumers must duck-type; ~10-20 file changes; not a 1-line patch.
- **C — Drop shape-violators at Stage 2 directly into `deterministically_rejected`.** Wrap the `NormalizedRatesheet.model_validate(body)` call in a `ValidationError` catcher that scans for shape failures, strips the offending lanes from `body["lanes"]`, and appends synthesized `RejectionRecord(rule_id="port_unknown_unlocode", …)` entries into `body["deterministically_rejected"]`. Pros: surgical; no schema touch. Cons: violates Phase 7's "Stage 4 is the sole source of rejections" invariant — Stage 2 would now emit rejections too; the 18a force-overwrite would need to be reverted (current code wipes `deterministically_rejected` immediately after Stage 2 builds the body); and the prompt's "Stage 4 will reject them" promise becomes a lie.

**Recommendation:** Option B is the only path that doesn't break a sibling invariant. It is non-trivial.

## Defect 20 — Stage 2 `ValidationError` is unhandled; jobs stick at `extracting`

**Severity:** High. Independent of Defect 19, this is a stack-hygiene gap that will resurface any time Stage 2 produces a Pydantic violation (e.g. an LLM ignores prompt constraints in any field, not just port codes).

### Symptom

Same as above — job remains at `status="extracting"`, no `failed` transition, no `_commit_failure` audit row. API `/v1/intake/jobs/<id>` returns `status: extracting` forever; user has no closure path.

### Root cause

`packages/ingest/tasks.py:240`:

```python
except (ExcelTooLargeError, ExtractionError) as exc:
    await _commit_failure(factory, job_id, "extract_failed", exc)
    ...
```

The handler catches `ExcelTooLargeError` and `ExtractionError`. Pydantic `ValidationError` raised from `extract_excel_payload`'s `NormalizedRatesheet.model_validate(body)` is neither — it propagates out of `_extract`, out of `asyncio.run(...)`, out of the Celery `extract_payload_task` (which has `max_retries=0`), and the task dies without ever calling `update_job_status(..., new_status="failed", completed=True)`.

The Phase 6.6 §6.3 failure-audit contract assumes any Stage 2 failure → `_commit_failure`, but the catcher's type list omits `ValidationError`.

### Design-judgment options

- **A — Widen the catcher.** Change `except (ExcelTooLargeError, ExtractionError)` to `except (ExcelTooLargeError, ExtractionError, ValidationError)`. Pros: 1-line patch; symmetric with `_commit_failure` semantics. Cons: bypasses the type contract — `ExtractionError` is the Phase 4 sentinel for "Stage 2 failed cleanly"; ValidationError can now leak operator-input shapes into the `_failure_payload` error string (PII risk — the regex literal `^[A-Z]{2}[A-Z0-9]{3}$` is fine but `input_value='ZZ@ZZ'` is operator-supplied content). Need to confirm `_failure_payload` PII scrubbing covers Pydantic error reprs.
- **B — Wrap `extract_excel_payload` to convert `ValidationError` → `ExtractionError`.** Inside `excel_extractor.py`, catch `ValidationError` around the `model_validate(body)` call and re-raise as `ExtractionError("stage2_pydantic_schema_violation: <count> error(s)")`. Pros: keeps the exception taxonomy clean; existing handler unchanged. Cons: this gets entangled with the Defect 19 fix because the resolution depends on whether bad-shape codes are supposed to fail validation or not.

**Recommendation:** Resolve Defect 19 first (B from the §19 options); Defect 20 is partially absorbed by that fix because shape-violating codes will no longer raise ValidationError at Stage 2. Keep Defect 20's resolution as a `ValidationError → ExtractionError` wrap inside `excel_extractor.py` for ANY remaining schema violations (the "true" failures) so the failure-audit contract is exhaustive.

## What is NOT broken

- Phase 7 §6.2 (Defect 18b EDIFACT DTM override) — verified live on `broken_malformed_edifact.edi`. Flash's hallucinated past validity_end was overridden by DTM+36:20261231. No validity_window_in_the_past hit. PASS.
- Phase 7 §6.3 (Defect 18c inline `OnrampAuditLog` writes) — successful BNR job ran through all 4 success-path tasks; F.5 audit-row count needs verification but worker logs show `_classify`/`_extract`/`_normalize`/`_validate` all succeeded in sequence.
- Phase 6.9 provenance (`lane_id` + value-citing `rule_description`) — present on BNR's `negative_base_rate` rejection.
- All Phase 6.5/6.6/6.8/6.9 invariants — untouched by V9; no regression observed in the BNR + BME paths.

## Required handoff

The fix CANNOT be applied within the V9 in-flight patch authority because:

1. Defect 19 touches Phase 2 hard invariant (`PortCode` schema is named in `ULTIMATE_PRD §3` and the model docstring as a "white-box anchor").
2. Defect 19's recommended fix (Option B — `RawPortCode`) is a 10-20-file refactor across Stage 2/3/4 and the test suite.
3. Defect 20's resolution is entangled with Defect 19.
4. Phase 7 §6.4's mocked test (`test_stage3_normalizer_passes_shape_violating_ports_to_stage4`) requires re-architecture — it cannot keep using `PortCode.model_construct(...)` and claim to test a live-stack contract.

This is a Phase 8 closure spec, not a V9 in-flight patch.

## Next step

Generate `PHASE_8_SPEC.md` (Step 2) covering:
- Defect 19 resolution per Option B (or an explicit reasoned override).
- Defect 20 resolution per its Option B.
- Re-architecture of Phase 7 §6.4's bypass-using mocked tests so they exercise the live Stage 2 → Stage 3 → Stage 4 contract end-to-end without `model_construct`.
- A regression test that submits the actual `broken_impossible_port_codes.xlsx` fixture against a mocked Vertex client and asserts the job reaches `status="completed"` with R1 `port_unknown_unlocode` rejections (not stuck at `extracting`, not raising ValidationError).
- Stage F.4 (only the BPC fixture re-run; BNR and BME PASSED at V9 and stand) + F.5 re-run after Phase 8 lands.

— Step 4 V9 halt, 2026-05-28.
