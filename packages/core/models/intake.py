"""Operator-grade intake models. Implements PHASE_5_SPEC.md §3.1."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.core.models.ratesheet import JobStatusLiteral


class IntakeJobRequest(BaseModel):
    """Operator-grade ingress (form-encoded multipart, separate from /v1/ingest)."""

    model_config = ConfigDict(extra="forbid")

    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    operator_email: str = Field(min_length=5, max_length=128)
    requested_slack_channel: str = Field(min_length=2, max_length=128)
    priority: Literal["normal", "rush"] = "normal"


class IntakeJobResponse(BaseModel):
    """202 body returned by POST /v1/intake/jobs."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatusLiteral
    submitted_by: str = Field(min_length=5, max_length=128)
    submitted_at: datetime


class ReviewAck(BaseModel):
    """Operator acknowledgment of a flagged lane outcome."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    lane_id: str
    decision: Literal["accept", "reject", "needs_prospect_clarification"]
    operator_email: str = Field(min_length=5, max_length=128)
    notes: str = Field(default="", max_length=512)
    acknowledged_at: datetime


class SignedUrlResponse(BaseModel):
    """Body returned by GET /v1/intake/jobs/{id}/result-url."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    url: str = Field(min_length=32, max_length=2048)
    expires_at: datetime
