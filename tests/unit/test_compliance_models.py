"""Pydantic strict-forbid tests. PHASE_1_SPEC §9 criterion 8."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.core.models.compliance import (
    ComplianceConfig,
    CustomerComplianceProfile,
)
from packages.core.models.health import BootValidatorResult, HealthResponse


def test_health_response_forbids_extra_fields() -> None:
    """HealthResponse rejects unexpected fields."""
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(
            {
                "status": "healthy",
                "version": "0.1.0",
                "region": "europe-west4",
                "timestamp": datetime.now(UTC).isoformat(),
                "validators": [],
                "extra_field": "should_be_rejected",
            }
        )


def test_boot_validator_result_constrains_exit_codes() -> None:
    """Only exit codes 1, 2, 3, 4 are allowed."""
    with pytest.raises(ValidationError):
        BootValidatorResult.model_validate(
            {
                "validator_name": "vertex_ai_handshake",
                "passed": True,
                "exit_code_on_failure": 5,
                "latency_ms": 1,
                "detail": "x",
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )


def test_compliance_config_forbids_extra_fields() -> None:
    """ComplianceConfig rejects unexpected fields."""
    with pytest.raises(ValidationError):
        ComplianceConfig.model_validate(
            {
                "project_id": "solvo-onramp-prod",
                "location": "europe-west4",
                "request_response_logging_disabled": True,
                "zdr_program_enrolled": True,
                "spurious": "x",
            }
        )


def test_customer_compliance_profile_enforces_iso_floor() -> None:
    """audit_log_retention_days must be at least 365 (ISO 27001 floor)."""
    with pytest.raises(ValidationError):
        CustomerComplianceProfile.model_validate(
            {"customer_id": "acme", "audit_log_retention_days": 30}
        )


def test_customer_compliance_profile_defaults() -> None:
    """Defaults match the schema in ULTIMATE_PRD §3.10.3."""
    profile = CustomerComplianceProfile(customer_id="acme")
    assert profile.raw_upload_retention_days == 7
    assert profile.normalized_output_retention_days == 90
    assert profile.archived_output_ttl_days == 180
    assert profile.audit_log_retention_days == 365
