"""Audit model strict-forbid coverage — PHASE_4_SPEC §8 criterion 13."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.core.models.audit import AccessLogEntry, AuditLogEntry


def test_audit_log_entry_forbids_extra_fields() -> None:
    """AuditLogEntry rejects unexpected fields."""
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(
            {
                "audit_id": 1,
                "job_id": "j",
                "actor": "system",
                "action": "validate_complete",
                "payload": {},
                "actor_principal": "system",
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
    """Action Literal rejects values outside the Phase 4 enum."""
    with pytest.raises(ValidationError):
        AuditLogEntry.model_validate(
            {
                "audit_id": 1,
                "job_id": "j",
                "actor": "system",
                "action": "made_up_action",
                "payload": {},
                "actor_principal": "system",
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
