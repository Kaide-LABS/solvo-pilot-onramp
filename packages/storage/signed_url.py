"""V4 signed-URL generator. Implements PHASE_5_SPEC.md §6.3.

Pure-Python wrapper around google-cloud-storage. Deterministic — same
inputs produce the same URL within the TTL window. The TTL is locked to
900 seconds (15 minutes); callers cannot lengthen it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

# Locked. Phase 6 may not extend this without spec revision — the 15-minute
# TTL is the security commitment in §3.10.3.
SIGNED_URL_TTL_SECONDS: Final[int] = 900


async def generate_v4_signed_url(
    *,
    bucket: str,
    blob_name: str,
    service_account: str,
    ttl_seconds: int = SIGNED_URL_TTL_SECONDS,
) -> tuple[str, datetime]:
    """Return (signed_url, expires_at) for the given bucket/blob.

    `service_account` is the impersonated signer's email (workload-identity
    binding in production). `ttl_seconds` defaults to the locked 900s.
    """
    if ttl_seconds != SIGNED_URL_TTL_SECONDS:
        raise ValueError(
            f"signed-URL TTL is locked at {SIGNED_URL_TTL_SECONDS}s; got {ttl_seconds}"
        )

    def _sync() -> tuple[str, datetime]:
        from google.cloud import storage  # type: ignore[attr-defined]

        from packages.core.settings import get_settings

        client = storage.Client(project=get_settings().gcp_project_id)
        blob = client.bucket(bucket).blob(blob_name)
        issued_at = datetime.now(UTC)
        url: str = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=ttl_seconds),
            method="GET",
            service_account_email=service_account,
        )
        return url, issued_at + timedelta(seconds=ttl_seconds)

    return await asyncio.to_thread(_sync)
