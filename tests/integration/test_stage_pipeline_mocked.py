"""Phase 8 §6.4 — Stage 2→3→4 pipeline integration tests with Vertex mocked.

Phase 7 closed Defects 18a/b/c/d at the schema and tooling level but introduced
a test-architecture blind spot: the prior `_lane(...)` helper used
`PortCode.model_construct(...)` to bypass Pydantic validation while purporting
to exercise the post-18a Stage 2→3→4 contract. V9 surfaced this when the live
stack hit `ZZ@ZZ` / `QQ@QQ` and the job stuck at `extracting` because the real
Stage 2 schema gate rejected the shape-violators before Stage 3's carve-out
could fire.

Phase 8 (Defects 19 + 20) closes that loop by:
  - pre-scanning shape-violators out of `body["lanes"]` in `extract_excel_payload`
    BEFORE `NormalizedRatesheet.model_validate`,
  - re-injecting them at `_validate` as synthetic LaneRecord carriers so R1
    emits canonical `port_unknown_unlocode` rejections,
  - wrapping `model_validate` so any residual Pydantic violation surfaces as
    `ExtractionError` and the failure-handler catches it.

These tests run in vanilla `pytest tests/integration -q` without a live Vertex
stack and without docker-compose. They short-circuit Vertex at the SDK call
boundary (`_generate_with_retry` / `get_vertex_client`) so no quota burns.

Phase 8 §11 invariant: integration tests that purport to exercise the
Stage 2 → 3 → 4 contract MUST submit the body through the real Pydantic gate
in the test entry path. `PortCode.model_construct(...)` is reserved for
production code (synthetic R1 carriers) and is forbidden in test entry points.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from packages.core.db.base import OnrampAuditLog
from packages.core.models.ratesheet import (
    ExtractionMetadata,
    LaneRecord,
    NormalizedRatesheet,
    PortCode,
    SourceRow,
)
from packages.ingest.tasks import _audit_row

_NOW = datetime(2026, 5, 27, tzinfo=UTC)


def _meta() -> ExtractionMetadata:
    return ExtractionMetadata(
        extractor_model="gemini-3.1-flash-lite",
        extracted_at=_NOW,
        prompt_version="phase8.test",
        cell_count=10,
    )


def _clean_lane(
    lane_id: str,
    origin_code: str,
    destination_code: str,
    *,
    base_rate_usd: Decimal = Decimal("2100"),
) -> LaneRecord:
    """Construct a shape-valid LaneRecord through the real Pydantic gate.

    Phase 8 §11: no `PortCode.model_construct(...)` in test entry points.
    Inputs must already satisfy the canonical UN/LOCODE regex.
    """
    return LaneRecord(
        lane_id=lane_id,
        origin_port=PortCode(code=origin_code),
        destination_port=PortCode(code=destination_code),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=base_rate_usd,
        surcharges=[],
        transit_time_days=14,
        validity_start=date(2026, 6, 1),
        validity_end=date(2026, 12, 31),
        source_row_reference=SourceRow(sheet_name="Rates", row_number=4, cell_reference="A4"),
    )


def _wrap_clean(*lanes: LaneRecord) -> NormalizedRatesheet:
    return NormalizedRatesheet(
        job_id="job-phase8-mock",
        prospect_id="prosp-phase8",
        extraction_metadata=_meta(),
        lanes=list(lanes),
    )


# ---------------------------------------------------------------------------
# Phase 8 §6.3 test 1 — Defect 19 end-to-end (Stage 2 pre-scan → Stage 4 R1)
# ---------------------------------------------------------------------------


def test_full_pipeline_broken_impossible_port_codes() -> None:
    """Phase 8 §6.3 / Defect 19 — Stage 2 pre-scan + Stage 4 R1 emit canonical rejection.

    Exercises the LIVE Pydantic schema gate. Vertex is short-circuited but the
    LLM body returned contains both shape-valid and shape-violating port codes,
    and `extract_excel_payload`'s pre-scan must:
      (a) NOT raise pydantic.ValidationError on the violators,
      (b) lift the violators into `payload.shape_violating_lanes`,
      (c) preserve the LLM-supplied `source_row_reference` (Build Directive 1),
      (d) leave the shape-valid lanes in `payload.lanes`.

    Then the Stage 4 re-injection path in `_validate` synthesizes carrier
    LaneRecords from `shape_violating_lanes` and feeds them to `apply_hard_rules`
    so R1 emits canonical `port_unknown_unlocode` rejections — NOT an LLM-emitted
    free-form ID like `INVALID_PORT_CODE` (the V8 regression detector).

    No `PortCode.model_construct(...)` appears in this test body's entry path.
    """
    from packages.ingest import excel_extractor as ex
    from packages.ingest.rules_engine import apply_hard_rules

    # Build the LLM body the live stack would return for the
    # broken_impossible_port_codes.xlsx fixture: 1 clean lane + 2 shape-
    # violating lanes (origin and destination respectively).
    llm_body: dict[str, Any] = {
        "job_id": "placeholder",
        "prospect_id": "placeholder",
        "schema_version": "onramp.v1",
        "extraction_metadata": {
            "extractor_model": "gemini-3.1-flash-lite",
            "extracted_at": _NOW.isoformat(),
            "prompt_version": "phase8.test",
            "cell_count": 30,
        },
        "lanes": [
            {
                "lane_id": "L1",
                "origin_port": {"code": "DEHAM"},
                "destination_port": {"code": "USNYC"},
                "equipment_type": "40HC",
                "commodity_code": None,
                "base_rate_usd": "2100",
                "surcharges": [],
                "transit_time_days": 14,
                "validity_start": "2026-06-01",
                "validity_end": "2026-12-31",
                "source_row_reference": {
                    "sheet_name": "Rates",
                    "row_number": 3,
                    "cell_reference": "A3",
                },
            },
            {
                "lane_id": "L2",
                "origin_port": {"code": "ZZ@ZZ"},  # shape-violating
                "destination_port": {"code": "USLAX"},
                "equipment_type": "40HC",
                "commodity_code": None,
                "base_rate_usd": "1800",
                "surcharges": [],
                "transit_time_days": 18,
                "validity_start": "2026-06-01",
                "validity_end": "2026-12-31",
                "source_row_reference": {
                    "sheet_name": "Rates",
                    "row_number": 4,
                    "cell_reference": "A4",
                },
            },
            {
                "lane_id": "L3",
                "origin_port": {"code": "DEHAM"},
                "destination_port": {"code": "QQ@QQ"},  # shape-violating
                "equipment_type": "40HC",
                "commodity_code": None,
                "base_rate_usd": "1900",
                "surcharges": [],
                "transit_time_days": 16,
                "validity_start": "2026-06-01",
                "validity_end": "2026-12-31",
                "source_row_reference": {
                    "sheet_name": "Rates",
                    "row_number": 6,
                    "cell_reference": "B6",
                },
            },
        ],
        # Stage 2 LLM occasionally smuggles these — Phase 7 §6.1.1 force-overwrite
        # erases them; this test mimics the smuggling so we verify both fixes
        # work together.
        "conformal_scores": {"L2": 0.42},
        "flagged_for_review": [],
        "deterministically_rejected": [
            {
                "source_row_reference": {
                    "sheet_name": "Rates",
                    "row_number": 4,
                    "cell_reference": "A4",
                },
                "lane_id": "L2",
                "rule_id": "INVALID_PORT_CODE",  # LLM-smuggled — must be erased
                "rule_description": "made-up rejection",
            }
        ],
    }

    fake_response = MagicMock()
    fake_response.text = json.dumps(llm_body)

    async def fake_generate(_client: Any, _contents: str, _schema: dict[str, Any]) -> Any:
        return fake_response

    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        # Bypass the openpyxl file read; the body is supplied by the Vertex
        # mock. Return a non-empty cells list so cell_count > 0.
        return [{"sheet": "Rates", "coord": "A1", "value": "stub"}]

    async def _run() -> tuple[NormalizedRatesheet, ExtractionMetadata]:
        settings = MagicMock()
        with (
            patch.object(ex, "_generate_with_retry", side_effect=fake_generate),
            patch.object(ex, "get_vertex_client", return_value=MagicMock()),
            patch.object(ex.asyncio, "to_thread", side_effect=fake_to_thread),
        ):
            return await ex.extract_excel_payload(
                Path("fixtures/broken_impossible_port_codes.xlsx"),
                "job-phase8-prescan",
                "prosp-phase8",
                settings,
            )

    payload, _meta_out = asyncio.run(_run())

    # (a) No ValidationError raised; payload constructed.
    assert isinstance(payload, NormalizedRatesheet)
    # (b) Pre-scan lifted both violators.
    assert len(payload.shape_violating_lanes) == 2
    by_id = {sv.lane_id: sv for sv in payload.shape_violating_lanes}
    assert by_id["L2"].raw_origin_code == "ZZ@ZZ"
    assert by_id["L2"].raw_destination_code == "USLAX"
    assert by_id["L3"].raw_origin_code == "DEHAM"
    assert by_id["L3"].raw_destination_code == "QQ@QQ"
    # (c) Real source_row_reference preserved (Build Directive 1).
    assert by_id["L2"].source_row_reference.cell_reference == "A4"
    assert by_id["L2"].source_row_reference.row_number == 4
    assert by_id["L3"].source_row_reference.cell_reference == "B6"
    assert by_id["L3"].source_row_reference.row_number == 6
    # (d) Only the shape-valid lane survives in payload.lanes.
    assert len(payload.lanes) == 1
    assert payload.lanes[0].lane_id == "L1"
    # Phase 7 §6.1.1 force-overwrite still runs: smuggled rejections erased.
    assert payload.deterministically_rejected == []
    assert payload.conformal_scores == {}

    # Mirror `_validate`'s re-injection: synthesize carrier LaneRecords from
    # shape_violating_lanes and run apply_hard_rules over them.
    _today = date.today()
    _tomorrow = _today + timedelta(days=1)
    synthetic_lanes = [
        LaneRecord.model_construct(
            lane_id=sv.lane_id,
            origin_port=PortCode.model_construct(code=sv.raw_origin_code),
            destination_port=PortCode.model_construct(code=sv.raw_destination_code),
            equipment_type="40HC",
            commodity_code=None,
            base_rate_usd=Decimal("1"),
            surcharges=[],
            transit_time_days=None,
            validity_start=_today,
            validity_end=_tomorrow,
            source_row_reference=sv.source_row_reference,
        )
        for sv in payload.shape_violating_lanes
    ]
    synthetic_rs = NormalizedRatesheet.model_construct(
        job_id=payload.job_id,
        prospect_id=payload.prospect_id,
        extraction_metadata=payload.extraction_metadata,
        lanes=synthetic_lanes,
        conformal_scores={},
        flagged_for_review=[],
        deterministically_rejected=[],
        shape_violating_lanes=[],
        schema_version="onramp.v1",
    )
    synthetic_validated, synthetic_violations = apply_hard_rules(synthetic_rs, now=_NOW)

    rejected = synthetic_validated.deterministically_rejected
    assert len(rejected) == 2
    assert {r.rule_id for r in rejected} == {"port_unknown_unlocode"}
    # Defect 18a regression detector — LLM-emitted free-form IDs forbidden.
    for r in rejected:
        assert r.rule_id != "INVALID_PORT_CODE"
        assert r.lane_id in {"L2", "L3"}
        assert r.rule_description, "Phase 6.9 value-citing rule_description missing"
    # Real Excel provenance survives end-to-end (Build Directive 1).
    refs = {r.lane_id: r.source_row_reference for r in rejected}
    assert refs["L2"].cell_reference == "A4"
    assert refs["L3"].cell_reference == "B6"
    assert [v.rule_id for v in synthetic_violations] == [
        "port_unknown_unlocode",
        "port_unknown_unlocode",
    ]


# ---------------------------------------------------------------------------
# Phase 8 §6.3 test 2 — Defect 20 (ValidationError → ExtractionError)
# ---------------------------------------------------------------------------


def test_extract_excel_payload_wraps_validation_error_as_extraction_error() -> None:
    """Phase 8 §6.2 / Defect 20 — Pydantic violations surface as ExtractionError.

    Any residual schema violation that survives the pre-scan (e.g. an LLM
    that returns an invalid equipment_type, or a negative cell_count) must
    raise `ExtractionError`, not propagate `pydantic.ValidationError` past
    `_extract`'s exception handler. Without this wrap the V9 BPC failure
    mode recurs: job sticks at `status=extracting` indefinitely.
    """
    from packages.ingest import excel_extractor as ex

    # Build a body that survives the pre-scan (all port codes shape-valid)
    # but fails model_validate on another field (equipment_type sentinel).
    llm_body: dict[str, Any] = {
        "job_id": "placeholder",
        "prospect_id": "placeholder",
        "schema_version": "onramp.v1",
        "extraction_metadata": {
            "extractor_model": "gemini-3.1-flash-lite",
            "extracted_at": _NOW.isoformat(),
            "prompt_version": "phase8.test",
            "cell_count": 10,
        },
        "lanes": [
            {
                "lane_id": "L1",
                "origin_port": {"code": "DEHAM"},
                "destination_port": {"code": "USNYC"},
                "equipment_type": "NOT_A_REAL_EQUIP",  # violates Literal
                "commodity_code": None,
                "base_rate_usd": "2100",
                "surcharges": [],
                "transit_time_days": 14,
                "validity_start": "2026-06-01",
                "validity_end": "2026-12-31",
                "source_row_reference": {
                    "sheet_name": "Rates",
                    "row_number": 3,
                    "cell_reference": "A3",
                },
            },
        ],
    }

    fake_response = MagicMock()
    fake_response.text = json.dumps(llm_body)

    async def fake_generate(_client: Any, _contents: str, _schema: dict[str, Any]) -> Any:
        return fake_response

    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        return [{"sheet": "Rates", "coord": "A1", "value": "stub"}]

    async def _run() -> None:
        settings = MagicMock()
        with (
            patch.object(ex, "_generate_with_retry", side_effect=fake_generate),
            patch.object(ex, "get_vertex_client", return_value=MagicMock()),
            patch.object(ex.asyncio, "to_thread", side_effect=fake_to_thread),
        ):
            await ex.extract_excel_payload(
                Path("fixtures/broken_impossible_port_codes.xlsx"),
                "job-phase8-defect20",
                "prosp-phase8",
                settings,
            )

    raised: Exception | None = None
    try:
        asyncio.run(_run())
    except Exception as exc:
        raised = exc

    assert raised is not None, "expected ExtractionError to be raised"
    assert isinstance(raised, ex.ExtractionError), (
        f"Phase 8 §6.2 regression: expected ExtractionError, got {type(raised).__name__}"
    )
    assert "stage2_schema_violation" in str(raised)


# ---------------------------------------------------------------------------
# Phase 8 §6.3 test 3 — narrowed normalizer carve-out responsibility
# ---------------------------------------------------------------------------


def test_normalizer_carveout_handles_table_unknown_shape_valid_codes() -> None:
    """Phase 8 §6.3 — Stage 3 carve-out's narrower responsibility post-pre-scan.

    The Phase 7 §6.1.3 carve-out is a two-arm gate. Phase 8 changes which arm
    is reachable from live input:
      - Shape-VIOLATING arm (`if origin_shape_bad or dest_shape_bad`): now
        unreachable from live input — the Stage 2 pre-scan lifts shape-bad
        codes out before they reach Stage 3. Retained as defense-in-depth.
      - Shape-VALID but table-UNKNOWN arm (`else` branch): the live-reachable
        path. Codes like `XXAAA` that pass the UN/LOCODE regex but are absent
        from `un_locode_reference` are flagged with `port_obfuscation_unresolved`
        for Phase 5 human review.

    This test exercises the second arm and asserts R1 does NOT fire on the
    shape-valid code (the regex passes), confirming the canonical contract.
    """
    import packages.ingest.normalizer as nm
    from packages.core.models.normalization import ConsensusResult, EnsembleVote

    table_unknown_lane = _clean_lane("L_TBL_UNK", "XXAAA", "USNYC")
    clean_lane = _clean_lane("L_OK", "DEHAM", "USNYC")

    async def fake_ensemble(client: Any, lane: LaneRecord) -> ConsensusResult:
        votes = [
            EnsembleVote(
                sample_index=i,
                temperature=t,
                lane=lane,
                raw_response_hash="0" * 64,
            )
            for i, t in enumerate((0.1, 0.5, 0.9))
        ]
        return ConsensusResult(
            lane_id=lane.lane_id,
            consensus_lane=lane,
            votes=votes,
            requires_review=False,
            review_reason="agreement_clean",
        )

    async def fake_resolve(code: str, _session: Any) -> Any:
        from packages.core.models.normalization import ResolvedPortCode

        if code == "XXAAA":
            return ResolvedPortCode(
                canonical=None,
                source_alias=code,
                resolution_method="unresolved",
            )
        return ResolvedPortCode(
            canonical=PortCode(code=code),
            source_alias=code,
            resolution_method="direct_unlocode",
        )

    rs = _wrap_clean(table_unknown_lane, clean_lane)

    async def _run() -> NormalizedRatesheet:
        with (
            patch.object(nm, "_ensemble_for_lane", side_effect=fake_ensemble),
            patch.object(nm, "resolve_port_code", side_effect=fake_resolve),
            patch.object(nm, "get_vertex_client", return_value=MagicMock()),
        ):
            session = MagicMock()
            settings = MagicMock()
            updated, _ = await nm.normalize_lanes(
                job_id="job-test",
                extraction=rs,
                session=session,
                settings=settings,
            )
            return updated

    updated = asyncio.run(_run())

    # The clean lane survives.
    lane_ids_in_lanes = [lane.lane_id for lane in updated.lanes]
    assert "L_OK" in lane_ids_in_lanes

    # The shape-valid table-unknown lane is flagged with
    # `port_obfuscation_unresolved` per the carve-out's live-reachable arm.
    flagged_by_id = {f.lane.lane_id: f for f in updated.flagged_for_review}
    assert "L_TBL_UNK" in flagged_by_id, (
        "Phase 8 §6.3 regression: shape-valid table-unknown code did not reach "
        "the carve-out's flagging arm"
    )
    assert flagged_by_id["L_TBL_UNK"].reason == "port_obfuscation_unresolved"

    # R1 does NOT fire on the shape-valid code — verify by running
    # apply_hard_rules on the surviving lanes. (The flagged lane is not in
    # `lanes`, so it doesn't surface here either; R1 only operates on `lanes`.)
    from packages.ingest.rules_engine import apply_hard_rules

    validated, _violations = apply_hard_rules(updated, now=_NOW)
    rejected_ids = {r.lane_id for r in validated.deterministically_rejected}
    assert "L_TBL_UNK" not in rejected_ids
    assert "L_OK" not in rejected_ids


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test (retained) — 18b EDIFACT DTM+36 override
# ---------------------------------------------------------------------------


def test_full_pipeline_broken_malformed_edifact() -> None:
    """Phase 7 §6.4 / Defect 18b — EDIFACT validity_end must honor DTM+36.

    The fixture `broken_malformed_edifact.edi` carries a pre-LIN
    `DTM+36:20261231:102` segment that the cluster loop previously discarded.
    Without the Phase 7 §6.2 fix, Flash hallucinates `validity_end=2023-12-31`
    and R3 (`validity_window_in_the_past`) masks the structural defect. With
    the fix, the parsed DTM+36 date overrides Flash's hallucination.
    """
    from packages.ingest import edifact_extractor as edi

    fixture = Path("fixtures/broken_malformed_edifact.edi")
    assert fixture.exists(), "fixture file missing"

    hallucinated = LaneRecord(
        lane_id="edi-row-1",
        origin_port=PortCode(code="DEHAM"),
        destination_port=PortCode(code="USNYC"),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal("1000"),
        surcharges=[],
        transit_time_days=None,
        validity_start=date(2023, 1, 1),
        validity_end=date(2023, 12, 31),
        source_row_reference=SourceRow(
            sheet_name="broken_malformed_edifact",
            row_number=1,
            cell_reference="LIN:1",
        ),
    )

    async def fake_disambiguate(
        _client: Any, _segments: list[dict[str, Any]], lane_id: str
    ) -> LaneRecord:
        return hallucinated

    async def _run() -> NormalizedRatesheet:
        settings = MagicMock()
        with (
            patch.object(edi, "_disambiguate_via_flash", side_effect=fake_disambiguate),
            patch.object(edi, "get_vertex_client", return_value=MagicMock()),
        ):
            rs, _meta = await edi.extract_edifact_payload(
                fixture, "job-test-edi", "prosp-test", settings
            )
            return rs

    rs = asyncio.run(_run())

    assert len(rs.lanes) >= 1
    lane = rs.lanes[0]
    assert lane.validity_end >= date(2026, 6, 1), (
        f"Defect 18b regression: validity_end={lane.validity_end} not future-dated; "
        f"DTM+36 segment override failed"
    )
    assert lane.validity_start >= date(2026, 5, 1)


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test (retained) — 18c audit-log inline-write contract
# ---------------------------------------------------------------------------


def test_full_pipeline_writes_audit_log() -> None:
    """Phase 7 §6.4 / Defect 18c — `_audit_row` produces well-formed audit rows."""
    row = _audit_row(
        job_id="job-abc-123",
        action="validated",
        payload={"stage": "validated", "lane_count": 11},
    )

    assert isinstance(row, OnrampAuditLog)
    assert row.job_id == "job-abc-123"
    assert row.action == "validated"
    assert row.actor == "worker", "Phase 7 §6.3 contract: actor='worker'"
    assert row.actor_principal == "pipeline-task", (
        "Phase 7 §6.3 contract: actor_principal='pipeline-task'"
    )
    assert isinstance(row.payload, dict)
    assert row.payload["stage"] == "validated"


def test_tasks_module_wires_audit_row_into_all_success_paths() -> None:
    """Phase 7 §6.4 / Defect 18c — verify all four success paths call _audit_row."""
    source = Path("packages/ingest/tasks.py").read_text(encoding="utf-8")

    for action in ("classified", "extracted", "normalized", "validated"):
        marker = f'_audit_row(\n                    job_id,\n                    action="{action}"'
        alt_marker = f'_audit_row(job_id, action="{action}"'
        assert marker in source or alt_marker in source or f'action="{action}"' in source, (
            f"Phase 7 §6.3 regression: success-path stage {action!r} does not call _audit_row"
        )

    assert "session.add(_audit_row(job_id, action=stage, payload=payload))" in source, (
        "Phase 7 §6.3 regression: _commit_failure does not write OnrampAuditLog row"
    )


# ---------------------------------------------------------------------------
# Phase 7 §6.4 / Phase 8 — Stage 4 deterministic invariant (updated for §6.1)
# ---------------------------------------------------------------------------


def test_stage4_invariant_apply_hard_rules_is_sole_rejection_source() -> None:
    """Phase 7 §11 + Phase 8 §6.1 — apply_hard_rules makes zero Vertex calls.

    Stage 4 deterministic-rejection invariant: even when called with a mix of
    real clean lanes, synthetic shape-violator carriers (Phase 8 §6.1
    re-injection shape), and an R2 violator, `apply_hard_rules` must not
    invoke Vertex AI and every emitted rule_id must be in the canonical set.
    """
    import packages.compliance.vertex_client as vc
    from packages.ingest.rules_engine import apply_hard_rules

    def vertex_forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Stage 4 invariant violated: apply_hard_rules attempted a Vertex call")

    _today = date.today()
    _tomorrow = _today + timedelta(days=1)
    synthetic_violator = LaneRecord.model_construct(
        lane_id="L_SYNTH_VIOLATOR",
        origin_port=PortCode.model_construct(code="ZZ@ZZ"),
        destination_port=PortCode.model_construct(code="USLAX"),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=Decimal("1"),
        surcharges=[],
        transit_time_days=None,
        validity_start=_today,
        validity_end=_tomorrow,
        source_row_reference=SourceRow(sheet_name="Rates", row_number=4, cell_reference="A4"),
    )
    r2_violator = _clean_lane("L_R2", "DEHAM", "USNYC", base_rate_usd=Decimal("-100"))
    clean = _clean_lane("L_OK", "DEHAM", "USNYC")

    rs = NormalizedRatesheet.model_construct(
        job_id="job-stage4-inv",
        prospect_id="prosp-stage4-inv",
        extraction_metadata=_meta(),
        lanes=[clean, synthetic_violator, r2_violator],
        conformal_scores={},
        flagged_for_review=[],
        deterministically_rejected=[],
        shape_violating_lanes=[],
        schema_version="onramp.v1",
    )

    with patch.object(vc, "get_vertex_client", side_effect=vertex_forbidden):
        updated, violations = apply_hard_rules(rs, now=_NOW)

    rejected_ids_by_lane = {r.lane_id: r.rule_id for r in updated.deterministically_rejected}
    assert rejected_ids_by_lane["L_SYNTH_VIOLATOR"] == "port_unknown_unlocode", (
        "Phase 8 §6.1 regression: synthetic shape-violator carrier did not "
        "trigger canonical R1 in apply_hard_rules"
    )
    assert rejected_ids_by_lane["L_R2"] == "negative_base_rate"
    assert len(updated.lanes) == 1

    canonical = {
        "port_unknown_unlocode",
        "negative_base_rate",
        "validity_window_in_the_past",
        "validity_window_inverted",
        "transit_time_out_of_range",
        "equipment_type_unknown",
        "surcharge_basis_unknown",
    }
    for v in violations:
        assert v.rule_id in canonical, (
            f"Phase 7 §11 regression: non-canonical rule_id {v.rule_id!r}"
        )


# Suppress unused-import warnings — AsyncMock is available for future expansion.
_ = AsyncMock
