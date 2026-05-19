"""Per-event-type outbox delivery. Implements PHASE_5_SPEC.md §6.4."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from packages.core.settings import Settings

_log = logging.getLogger(__name__)


async def deliver_slack_post(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Post a Block Kit message to Slack.

    Idempotency: keyed by (channel, job_id) — the caller is responsible for
    pre-flighting via the Redis lock. Slack itself returns the same `ts` for
    re-posts within the same thread when the bot uses the same metadata.
    """
    from packages.slack.client import get_slack_client

    client = get_slack_client(settings)
    response = await client.chat_postMessage(
        channel=payload["channel"],
        blocks=payload.get("blocks"),
        text=payload.get("text", "Solvo Onramp result"),
    )
    return {"ts": response.get("ts"), "channel": payload["channel"]}


async def deliver_webhook_callback(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Optional outbound webhook (gated by Settings.enable_webhook_callbacks).

    Idempotency key sent as X-Idempotency-Key header.
    """
    if not settings.enable_webhook_callbacks:
        return {"skipped": True, "reason": "webhook_callbacks_disabled"}
    import httpx

    body = json.dumps(payload.get("body", {})).encode("utf-8")
    idem_key = hashlib.sha256(body).hexdigest()
    async with httpx.AsyncClient(timeout=10.0) as http:
        response = await http.post(
            payload["url"],
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Idempotency-Key": idem_key,
            },
        )
    return {"status_code": response.status_code}


async def deliver_signed_url_create(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Generate the signed URL eagerly (so the audit row pins what was issued)."""
    from packages.storage.signed_url import generate_v4_signed_url

    url, expires_at = await generate_v4_signed_url(
        bucket=settings.gcs_bucket_outputs,
        blob_name=payload["blob_name"],
        service_account=settings.gcs_signer_service_account,
    )
    return {"url": url, "expires_at": expires_at.isoformat()}


async def deliver_audit_log(payload: dict[str, Any], _settings: Settings) -> dict[str, Any]:
    """audit_log delivery is a no-op — the row already lives in onramp_audit_log."""
    _log.debug("audit_log delivered (no-op): %s", payload.get("stage"))
    return {"delivered": True}


async def deliver_access_log(payload: dict[str, Any], _settings: Settings) -> dict[str, Any]:
    """access_log delivery is a no-op — the row already lives in onramp_access_log."""
    _log.debug("access_log delivered (no-op): %s", payload.get("route"))
    return {"delivered": True}
