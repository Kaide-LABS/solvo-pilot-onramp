"""Audit model strict-forbid coverage — PHASE_4_SPEC §8 criterion 13.

Phase 9.1 (Defect 22): the `AuditLogEntry` vocabulary is reconciled to the live
pipeline writer (`packages/ingest/tasks.py:_audit_row`, Phase 7 §6.3) — actor
`worker`, actions `classified|extracted|normalized|validated` (success) and
`extract_failed|normalize_failed|validate_failed` (failure). The original
Phase 4 §3.1 placeholder vocabulary (`*_complete`, actor `system`) was never
written and is gone; these tests assert the reconciled contract and lock it
against re-drift.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.core.models.audit import AccessLogEntry, AuditLogEntry


def test_audit_log_entry_forbids_extra_fields() -> None:
    """AuditLogEntry rejects unexpected fields (on otherwise-valid live data)."""
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(
            {
                "audit_id": 1,
                "job_id": "j",
                "actor": "worker",
                "action": "validated",
                "payload": {},
                "actor_principal": "pipeline-task",
                "occurred_at": datetime.now(UTC).isoformat(),
                "extra_field": "rejected",
            }
        )


def test_access_log_entry_rejects_unknown_route() -> None:
    """The route Literal rejects routes outside the Phase 4 catalogue."""
    with pytest.raises(ValidationError):
        AccessLogEntry.model_validate(
            {
                "access_id": 1,
                "job_id": "j",
                "principal": "ops@kaide.so",
                "route": "/v1/some/unknown/route",
                "accessed_at": datetime.now(UTC).isoformat(),
                "response_status": 200,
            }
        )


def test_audit_log_entry_rejects_unknown_action() -> None:
    """Action Literal still bites — the reconciliation widened the vocabulary to
    truth, it did NOT remove validation."""
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(
            {
                "audit_id": 1,
                "job_id": "j",
                "actor": "worker",
                "action": "banana",
                "payload": {},
                "actor_principal": "pipeline-task",
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )


@pytest.mark.parametrize(
    "action",
    [
        "classified",
        "extracted",
        "normalized",
        "validated",
        "extract_failed",
        "normalize_failed",
        "validate_failed",
    ],
)
def test_audit_log_entry_accepts_live_pipeline_row(action: str) -> None:
    """Phase 9.1 (Defect 22) regression detector: a realistic row written by the
    live pipeline writer (`_audit_row`, Phase 7 §6.3) MUST validate through the
    read-model. This is what the audit read endpoint serialises; if a future
    Phase-4-style edit reintroduces the drift, this test goes red before HTTP
    422 reaches an operator.
    """
    entry = AuditLogEntry.model_validate(
        {
            "audit_id": 7,
            "job_id": "7c042249a37b40379301a45b9e7b6116",
            "actor": "worker",
            "action": action,
            "payload": {"stage": action, "lane_count": 3},
            "actor_principal": "pipeline-task",
            "occurred_at": datetime.now(UTC).isoformat(),
            "request_id": None,
        }
    )
    assert entry.actor == "worker"
    assert entry.action == action
    assert entry.actor_principal == "pipeline-task"


def test_audit_log_entry_rejects_stale_phase4_vocabulary() -> None:
    """The dead Phase 4 §3.1 placeholder vocabulary must NOT validate — a single
    coherent vocabulary, not two. `validate_complete` / actor `system` are gone.
    """
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(
            {
                "audit_id": 1,
                "job_id": "j",
                "actor": "system",
                "action": "validate_complete",
                "payload": {},
                "actor_principal": "pipeline-task",
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
