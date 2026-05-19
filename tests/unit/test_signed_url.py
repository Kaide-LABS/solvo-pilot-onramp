"""Signed URL TTL pin. PHASE_5_SPEC §8 criterion 5."""

from __future__ import annotations

import pytest

from packages.storage.signed_url import SIGNED_URL_TTL_SECONDS, generate_v4_signed_url


def test_signed_url_ttl_pinned_to_900() -> None:
    """The locked TTL constant is exactly 900 seconds."""
    assert SIGNED_URL_TTL_SECONDS == 900


@pytest.mark.asyncio
async def test_signed_url_rejects_overridden_ttl() -> None:
    """Callers cannot lengthen the TTL — passing a different value raises ValueError."""
    with pytest.raises(ValueError, match="locked"):
        await generate_v4_signed_url(
            bucket="b",
            blob_name="x.json",
            service_account="signer@example.com",
            ttl_seconds=3600,
        )
