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
    expected_alembic_head: str = "0001_initial"

    # Redis
    redis_url: str

    # Compliance — see docs/compliance_setup.md for ops responsibilities.
    vertex_ai_zdr_enrolled: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton.

    The lru_cache means env-var reads happen exactly once per process; tests
    that need fresh settings must call get_settings.cache_clear() first.
    """
    return Settings()  # type: ignore[call-arg]
