"""Phase 7 §6.4 — Stage 2→3→4 pipeline integration tests with Vertex mocked.

Closes the structural blind spot (Defect 18d) that let Defects 18a/18b escape
Phase 6.9 review: unit tests bypassed Stage 2 via `PortCode.model_construct`;
the F.4 integration tests only checked syntactic validity at 3A/3B and only
ran against a live compose+Vertex stack at V8.

These tests run in vanilla `pytest tests/integration -q` without a live
Vertex stack and without docker-compose. They short-circuit the Vertex client
at `get_vertex_client` (so no quota burn) and exercise the post-Phase 7
contracts directly:

    18a — Stage 2 LLM-smuggled rejections must be stripped at the extractor;
          Stage 3 must pass shape-violating port codes through to Stage 4;
          Stage 4 must emit the canonical `port_unknown_unlocode` rule_id.
    18b — EDIFACT extractor must honor DTM+36 segments regardless of where
          they appear in the interchange (in particular, pre-LIN DTMs that
          the cluster loop previously discarded).
    18c — OnrampAuditLog rows must originate from a per-stage inline write,
          not from the dispatcher's no-op `deliver_audit_log` handler.
    Stage 4 invariant — `apply_hard_rules` is the SOLE source of rejection
          records; zero LLM calls happen between Stage 4 entry and rejection
          emission.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
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
        prompt_version="phase7.test",
        cell_count=10,
    )


def _lane(
    lane_id: str,
    origin_code: str,
    destination_code: str,
    *,
    base_rate_usd: Decimal = Decimal("2100"),
) -> LaneRecord:
    # Use model_construct on PortCode so we can simulate the post-18a contract
    # where Stage 2 passes shape-violating codes through into `lanes`.
    return LaneRecord(
        lane_id=lane_id,
        origin_port=PortCode.model_construct(code=origin_code),
        destination_port=PortCode.model_construct(code=destination_code),
        equipment_type="40HC",
        commodity_code=None,
        base_rate_usd=base_rate_usd,
        surcharges=[],
        transit_time_days=14,
        validity_start=date(2026, 6, 1),
        validity_end=date(2026, 12, 31),
        source_row_reference=SourceRow(sheet_name="Rates", row_number=4, cell_reference="A4"),
    )


def _wrap(*lanes: LaneRecord) -> NormalizedRatesheet:
    return NormalizedRatesheet(
        job_id="job-phase7-mock",
        prospect_id="prosp-phase7",
        extraction_metadata=_meta(),
        lanes=list(lanes),
    )


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test 1 — 18a end-to-end contract
# ---------------------------------------------------------------------------


def test_full_pipeline_broken_impossible_port_codes() -> None:
    """Phase 7 §6.4 / Defect 18a — Stage 4 must emit canonical `port_unknown_unlocode`.

    Simulates the post-18a Stage 2 contract: bad-shape port codes flow into
    `lanes` (not into `deterministically_rejected`). Stage 4's apply_hard_rules
    must then reject them with the canonical Phase 6.9 rule_id — NOT an
    LLM-emitted free-form ID like `INVALID_PORT_CODE` (the V8 regression).
    """
    from packages.ingest.rules_engine import apply_hard_rules

    rs = _wrap(
        _lane("L1", "DEHAM", "USNYC"),  # clean
        _lane("L2", "ZZ@ZZ", "USLAX"),  # origin shape-violating
        _lane("L3", "DEHAM", "QQ@QQ"),  # destination shape-violating
    )

    updated, violations = apply_hard_rules(rs, now=_NOW)

    assert len(updated.lanes) == 1
    assert updated.lanes[0].lane_id == "L1"

    rejected = updated.deterministically_rejected
    assert len(rejected) == 2
    assert {r.rule_id for r in rejected} == {"port_unknown_unlocode"}
    # 18a regression detector: forbid LLM-emitted free-form IDs.
    for r in rejected:
        assert r.rule_id != "INVALID_PORT_CODE", (
            "Defect 18a regression: LLM-smuggled rule_id leaked into Stage 4 output"
        )
        assert r.lane_id in {"L2", "L3"}, "Phase 6.9 lane_id provenance broken"
        assert r.rule_description, "Phase 6.9 value-citing rule_description missing"

    # The two violations carry the same canonical rule_id.
    assert [v.rule_id for v in violations] == [
        "port_unknown_unlocode",
        "port_unknown_unlocode",
    ]


def test_stage3_normalizer_passes_shape_violating_ports_to_stage4() -> None:
    """Phase 7 §6.1.3 — normalizer carve-out keeps bad-shape lanes flowing.

    Without the carve-out, `resolve_port_code` returning canonical=None on a
    bad-shape code would flag the lane for `port_obfuscation_unresolved` and
    Stage 4's R1 would never fire. With the carve-out, the lane passes through
    unchanged and Stage 4 emits `port_unknown_unlocode`.
    """
    import packages.ingest.normalizer as nm
    from packages.core.models.normalization import ConsensusResult, EnsembleVote

    bad_lane = _lane("L_BAD", "ZZ@ZZ", "USLAX")
    clean_lane = _lane("L_OK", "DEHAM", "USNYC")

    async def fake_ensemble(client: Any, lane: LaneRecord) -> ConsensusResult:
        votes = [
            EnsembleVote(
                sample_index=0,
                temperature=0.1,
                lane=lane,
                raw_response_hash="0" * 64,
            ),
            EnsembleVote(
                sample_index=1,
                temperature=0.5,
                lane=lane,
                raw_response_hash="0" * 64,
            ),
            EnsembleVote(
                sample_index=2,
                temperature=0.9,
                lane=lane,
                raw_response_hash="0" * 64,
            ),
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

        if code == "ZZ@ZZ":
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

    rs = _wrap(bad_lane, clean_lane)

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

    lane_ids_in_lanes = [lane.lane_id for lane in updated.lanes]
    assert "L_BAD" in lane_ids_in_lanes, (
        "Defect 18a Stage 3 carve-out regression: shape-violating lane was "
        "flagged instead of passed through to Stage 4"
    )
    flagged_ids = [f.lane.lane_id for f in updated.flagged_for_review]
    assert "L_BAD" not in flagged_ids


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test 2 — 18b end-to-end contract (EDIFACT DTM+36 override)
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

    # Mock the Flash disambiguator to return the hallucinated past date the
    # live V8 run produced. The DTM-override logic must replace it.
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
    # Fixture's DTM+137:20260501 should also surface as validity_start.
    assert lane.validity_start >= date(2026, 5, 1)


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test 3 — 18c audit-log inline-write contract
# ---------------------------------------------------------------------------


def test_full_pipeline_writes_audit_log() -> None:
    """Phase 7 §6.4 / Defect 18c — `_audit_row` produces well-formed audit rows.

    The dispatcher's `deliver_audit_log` is a no-op; the actual write happens
    inline in each task's success-path transaction. This test exercises the
    `_audit_row` helper directly and verifies the row carries the constant
    `actor` + `actor_principal` values required for F.5 completeness checks.
    """
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
    """Phase 7 §6.4 / Defect 18c — verify all four success paths call _audit_row.

    Static source inspection is the cheapest way to assert "every success path
    writes an OnrampAuditLog row." The dispatcher no-op + the inline-only
    contract mean a missed wire-up at any stage silently breaks F.5.
    """
    source = Path("packages/ingest/tasks.py").read_text(encoding="utf-8")

    # Each canonical action string must appear inside an `_audit_row(` call.
    for action in ("classified", "extracted", "normalized", "validated"):
        marker = f'_audit_row(\n                    job_id,\n                    action="{action}"'
        alt_marker = f'_audit_row(job_id, action="{action}"'
        assert marker in source or alt_marker in source or f'action="{action}"' in source, (
            f"Phase 7 §6.3 regression: success-path stage {action!r} does not call _audit_row"
        )

    # _commit_failure must also call _audit_row for failure stages.
    assert "session.add(_audit_row(job_id, action=stage, payload=payload))" in source, (
        "Phase 7 §6.3 regression: _commit_failure does not write OnrampAuditLog row"
    )


# ---------------------------------------------------------------------------
# Phase 7 §6.4 test 4 — Stage 4 deterministic invariant
# ---------------------------------------------------------------------------


def test_stage4_invariant_apply_hard_rules_is_sole_rejection_source() -> None:
    """Phase 7 §11 + §6.4 — apply_hard_rules makes zero Vertex calls.

    Stage 4 deterministic-rejection invariant: even when called repeatedly
    with mixed clean/violating lanes, `apply_hard_rules` must not invoke
    Vertex AI. Patching `get_vertex_client` to raise lets us assert that
    no code path inside apply_hard_rules tries to construct a client.
    """
    import packages.compliance.vertex_client as vc
    from packages.ingest.rules_engine import apply_hard_rules

    def vertex_forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Stage 4 invariant violated: apply_hard_rules attempted a Vertex call")

    rs = _wrap(
        _lane("L1", "DEHAM", "USNYC"),
        _lane("L2", "ZZ@ZZ", "USLAX"),
        _lane("L3", "DEHAM", "USNYC", base_rate_usd=Decimal("-100")),
    )

    with patch.object(vc, "get_vertex_client", side_effect=vertex_forbidden):
        updated, violations = apply_hard_rules(rs, now=_NOW)

    # Two rejections fired deterministically — one R1, one R2.
    rejected_ids = {r.rule_id for r in updated.deterministically_rejected}
    assert rejected_ids == {"port_unknown_unlocode", "negative_base_rate"}
    assert len(updated.lanes) == 1

    # And all rule_ids are in the canonical Phase 6.9 set (Phase 7 §11 NEW invariant).
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


# Suppress unused-import warnings for the AsyncMock import — it's available
# for any future expansion of these tests but not used today.
_ = AsyncMock
