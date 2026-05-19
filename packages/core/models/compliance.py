"""Compliance configuration models. Implements PHASE_1_SPEC.md §3.2.

Mirrors the schema in ULTIMATE_PRD §3.10.3 for CustomerComplianceProfile.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComplianceConfig(BaseModel):
    """Project-level Vertex AI compliance configuration.

    Loaded once at container boot. Validates project-level zero-retention
    state rather than per-call SDK flags (see PHASE_1_SPEC.md §0.5).
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=6, max_length=64)
    location: Literal["europe-west4"]
    request_response_logging_disabled: bool
    zdr_program_enrolled: bool
    publisher_models_configured: list[str] = Field(default_factory=list)


class CustomerComplianceProfile(BaseModel):
    """Per-customer retention overrides loaded from config at engagement init."""

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(min_length=3, max_length=64)
    raw_upload_retention_days: int = Field(default=7, ge=1, le=30)
    normalized_output_retention_days: int = Field(default=90, ge=30, le=365)
    archived_output_ttl_days: int = Field(default=180, ge=90, le=730)
    audit_log_retention_days: int = Field(default=365, ge=365, le=2555)
