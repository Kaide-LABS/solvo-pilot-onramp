"""Audit and access log models. Implements PHASE_4_SPEC.md §3.1.

Append-only at the application layer (database-level role enforcement is
Phase 6 per ULTIMATE_PRD §3.10.4).

Phase 9.1 (Defect 22): the `AuditLogEntry` vocabulary (`AuditAction` + `actor`)
is reconciled to the live pipeline writer (`packages/ingest/tasks.py:_audit_row`,
Phase 7 §6.3), the sole producer of `OnrampAuditLog` rows. The original Phase 4
§3.1 placeholder vocabulary was never written and made the audit read endpoint
return HTTP 422 on every real job. The `AccessLogEntry`/`AuditRoute` path has no
row writer and no reader endpoint, so it is left as-is (only `/internal/v1/audit/{id}`
is ever emitted, and it is already in the Literal).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Phase 9.1 (Defect 22): EXACTLY the values the live writer puts in
# `OnrampAuditLog.action` — four success transitions plus three failure
# transitions emitted by `_commit_failure`. One coherent vocabulary, not two:
# the old `*_complete` long-forms were never written and are deleted. The
# `ingress_received` stage exists only in an outbox payload, never an audit row,
# so it is intentionally absent here.
AuditAction = Literal[
    "classified",
    "extracted",
    "normalized",
    "validated",
    "extract_failed",
    "normalize_failed",
    "validate_failed",
]

AuditRoute = Literal[
    "/v1/jobs/{id}/status",
    "/v1/jobs/{id}/result",
    "/internal/v1/audit/{id}",
]


class AuditLogEntry(BaseModel):
    """One row of the §3.10.4 append-only audit trail."""

    model_config = ConfigDict(extra="forbid")

    audit_id: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=64)
    # Phase 9.1 (Defect 22): the worker is the sole writer of audit rows
    # (Phase 7 §6.3); `actor_principal` stays a free str ("pipeline-task").
    actor: Literal["worker"]
    action: AuditAction
    payload: dict[str, Any]
    actor_principal: str = Field(max_length=128)
    occurred_at: datetime
    request_id: str | None = Field(default=None, max_length=64)


class AccessLogEntry(BaseModel):
    """One row of onramp_access_log — who fetched what, when."""

    model_config = ConfigDict(extra="forbid")

    access_id: int = Field(ge=1)
    job_id: str = Field(min_length=1, max_length=64)
    principal: str = Field(min_length=1, max_length=128)
    route: AuditRoute
    accessed_at: datetime
    response_status: int = Field(ge=100, le=599)
