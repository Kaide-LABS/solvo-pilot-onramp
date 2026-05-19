"""Lifecycle / retention models. Implements PHASE_6_SPEC.md §3."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArchiveCandidate(BaseModel):
    """One row selected by retention_enforcer for archive."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    completed_at: datetime
    archive_blob_name: str = Field(min_length=4, max_length=256)
    source_table: Literal["onramp_outputs", "onramp_audit_log"]


class RetentionAssertion(BaseModel):
    """Boot-time assertion that live config respects §3.10.3 retention floors.

    Each window is pinned via Literal so accidental drift through env vars
    fails fast at Pydantic validation, before the boot validator even runs.
    """

    model_config = ConfigDict(extra="forbid")

    raw_upload_retention_days: Literal[7]
    normalized_output_retention_days: Literal[90]
    archived_output_ttl_days: Literal[180]
    audit_log_retention_days: Literal[365]
