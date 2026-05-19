"""Intake model strict-forbid + structural coverage. PHASE_5_SPEC §8."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from packages.core.models.intake import (
    IntakeJobRequest,
    IntakeJobResponse,
    ReviewAck,
    SignedUrlResponse,
)


def test_intake_job_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IntakeJobRequest.model_validate(
            {
                "prospect_id": "ACME",
                "prospect_name": "Acme",
                "operator_email": "ops@kaide.so",
                "requested_slack_channel": "#pilot-onramp",
                "priority": "normal",
                "unexpected": True,
            }
        )


def test_intake_job_request_rejects_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        IntakeJobRequest.model_validate(
            {
                "prospect_id": "ACME",
                "prospect_name": "Acme",
                "operator_email": "ops@kaide.so",
                "requested_slack_channel": "#pilot-onramp",
                "priority": "URGENT",
            }
        )


def test_review_ack_rejects_unknown_decision() -> None:
    with pytest.raises(ValidationError):
        ReviewAck.model_validate(
            {
                "job_id": "j",
                "lane_id": "L1",
                "decision": "maybe",
                "operator_email": "ops@kaide.so",
                "notes": "",
                "acknowledged_at": datetime.now(UTC).isoformat(),
            }
        )


def test_intake_job_response_carries_full_status_literal() -> None:
    """The status field accepts the full job lifecycle states (mirrors ratesheet.JobStatusLiteral)."""
    resp = IntakeJobResponse(
        job_id="j",
        status="validating",
        submitted_by="ops@kaide.so",
        submitted_at=datetime.now(UTC),
    )
    assert resp.status == "validating"


def test_signed_url_response_url_min_length_enforced() -> None:
    with pytest.raises(ValidationError):
        SignedUrlResponse.model_validate(
            {"job_id": "j", "url": "short", "expires_at": datetime.now(UTC).isoformat()}
        )
