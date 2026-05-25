"""GCS upload helpers. Implements PHASE_5_SPEC.md §1 + PHASE_6_8_SPEC.md §6.2.5.

`upload_blob` is the Phase 5 helper used by packages/lifecycle/archive.py for
the archive-cold-jobs flow (relies on default ADC, no explicit project).

`upload_normalized_json` (Phase 6.8 §6.2.5) is invoked by the dispatcher's
`deliver_upload_result` handler. It mirrors packages/storage/signed_url.py's
credential pattern — per-call google.auth.default() + creds.refresh() with
explicit credentials=creds on the storage.Client — because the local-compose
worker's ADC is user OAuth (no private key); the explicit project +
credentials pair is the production-grade shape.
"""

from __future__ import annotations

import asyncio


async def upload_blob(
    *, bucket: str, blob_name: str, payload: bytes, content_type: str = "application/json"
) -> None:
    """Upload `payload` bytes to gs://{bucket}/{blob_name}. Sync SDK wrapped in to_thread."""

    def _sync() -> None:
        from google.cloud import storage  # type: ignore[attr-defined]

        client = storage.Client()
        blob = client.bucket(bucket).blob(blob_name)
        blob.upload_from_string(payload, content_type=content_type)

    await asyncio.to_thread(_sync)


async def upload_normalized_json(
    *,
    bucket: str,
    blob_name: str,
    payload: bytes,
    content_type: str = "application/json",
) -> None:
    """Upload `payload` to gs://<bucket>/<blob_name>.

    Uses `Cache-Control: no-cache, max-age=0` so re-runs of a job within the
    900s signed-URL TTL see the freshly uploaded blob, not a cached copy.
    No inner retry — the outbox dispatcher owns retry-with-attempts semantics
    (PHASE_6_8_SPEC §6.2.5).
    """

    def _sync() -> None:
        import google.auth
        import google.auth.transport.requests
        from google.cloud import storage  # type: ignore[attr-defined]

        from packages.core.settings import get_settings

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())  # type: ignore[no-untyped-call]

        client = storage.Client(project=get_settings().gcp_project_id, credentials=creds)
        blob = client.bucket(bucket).blob(blob_name)
        blob.cache_control = "no-cache, max-age=0"
        blob.upload_from_string(payload, content_type=content_type)

    await asyncio.to_thread(_sync)
