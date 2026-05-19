"""Audit and access log models. Implements PHASE_4_SPEC.md §3.1.

Append-only at the application layer (database-level role enforcement is
Phase 6 per ULTIMATE_PRD §3.10.4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AuditAction = Literal[
    "ingress_received",
    "classify_complete",
    "extract_complete",
    "normalize_complete",
    "validate_complete",
    "correction_triggered",
    "clarification_drafted",
    "result_delivered",
    "review_acknowledged",
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
    actor: Literal["system", "operator", "external_webhook"]
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
