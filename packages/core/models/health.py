"""Health and boot-validator response models. Implements PHASE_1_SPEC.md §3.1."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BootValidatorResult(BaseModel):
    """Result of a single container-boot validator check.

    Each of the four validators emits one of these. Aggregated into HealthResponse.
    """

    model_config = ConfigDict(extra="forbid")

    validator_name: Literal[
        "vertex_ai_handshake",
        "postgres_alembic_head",
        "un_locode_table_integrity",
        "vertex_ai_compliance_handshake",
    ]
    passed: bool
    exit_code_on_failure: Literal[1, 2, 3, 4]
    latency_ms: int = Field(ge=0, le=30_000)
    detail: str = Field(max_length=512)
    checked_at: datetime


class HealthResponse(BaseModel):
    """Aggregate health response for /v1/health and /v1/health/ready."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    region: Literal["europe-west4"]
    timestamp: datetime
    validators: list[BootValidatorResult]
