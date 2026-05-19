"""GCS blob upload helper. Implements PHASE_5_SPEC.md §1."""

from __future__ import annotations

import asyncio


async def upload_blob(
    *, bucket: str, blob_name: str, payload: bytes, content_type: str = "application/json"
) -> None:
    """Upload `payload` bytes to gs://{bucket}/{blob_name}. Sync SDK wrapped in to_thread."""

    def _sync() -> None:
        from google.cloud import storage  # type: ignore[import-not-found]

        client = storage.Client()
        blob = client.bucket(bucket).blob(blob_name)
        blob.upload_from_string(payload, content_type=content_type)

    await asyncio.to_thread(_sync)
