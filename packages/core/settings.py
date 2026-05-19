"""Application settings loaded from environment variables.

Implements PHASE_1_SPEC.md §7.3.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration. Loaded once via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    environment: Literal["development", "staging", "production"] = "development"
    release_version: str = Field(default="0.1.0-dev")

    # GCP / Vertex AI — region binding is non-negotiable per ULTIMATE_PRD §3.2.
    gcp_project_id: str
    vertex_location: Literal["europe-west4"] = "europe-west4"

    # Postgres
    postgres_dsn_async: str
    postgres_dsn_sync: str
    expected_alembic_head: str = "0004_intake_review"

    # Redis
    redis_url: str

    # Compliance — see docs/compliance_setup.md for ops responsibilities.
    vertex_ai_zdr_enrolled: bool = False

    # Phase 4 internal-audit route bearer. The bearer is compared against the
    # GCP service-account email this principal is configured with; mismatches
    # return 403. Production deployments supply this via Cloud Run secret ref.
    internal_admin_principal: str = "ops@kaide.so"
    internal_admin_token: str = ""  # empty = route returns 403 unconditionally

    # Phase 5 — Slack + signed URL + dispatcher configuration.
    slack_signing_secret: str = ""
    slack_bot_token: str = ""
    gcs_bucket_outputs: str = "solvo-onramp-outputs"
    gcs_signer_service_account: str = ""
    enable_webhook_callbacks: bool = False

    # Phase 6 lifecycle / archive configuration. The retention floors are
    # pinned in packages/core/models/lifecycle.py:RetentionAssertion; these
    # settings expose the bucket + window for the daily Celery beat task.
    gcs_archive_bucket: str = "solvo-onramp-archive"
    archive_age_days: int = 90
    retention_config_path: str = "fixtures/retention_v1.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton.

    The lru_cache means env-var reads happen exactly once per process; tests
    that need fresh settings must call get_settings.cache_clear() first.
    """
    return Settings()  # type: ignore[call-arg]
