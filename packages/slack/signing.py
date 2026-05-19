"""Slack X-Slack-Signature verification. Implements PHASE_5_SPEC.md §6.1.

Pure Python, deterministic, zero LLM. Uses hmac.compare_digest to prevent
timing-attack leakage.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final, Literal

REPLAY_WINDOW_SECONDS: Final[int] = 300  # ±5 minutes


class SlackSignatureError(Exception):
    """Raised when the signature is malformed, mismatched, or stale."""


def verify_signature(
    *,
    secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
    now: float | None = None,
) -> Literal[True]:
    """Verify the Slack signature. Raise on failure; return True on success.

    Mirrors the documented Slack algorithm:
      sig_basestring = f"v0:{timestamp}:{body}"
      expected = "v0=" + HMAC_SHA256(secret, sig_basestring).hexdigest()
      hmac.compare_digest(expected, signature)
    """
    if not secret:
        raise SlackSignatureError("slack signing secret not configured")
    try:
        ts_int = int(timestamp)
    except ValueError as exc:
        raise SlackSignatureError("invalid timestamp header") from exc

    current = now if now is not None else time.time()
    if abs(current - ts_int) > REPLAY_WINDOW_SECONDS:
        raise SlackSignatureError("timestamp outside replay window")

    basestring = b"v0:" + timestamp.encode("ascii") + b":" + body
    digest = hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    if not hmac.compare_digest(expected, signature):
        raise SlackSignatureError("signature mismatch")
    return True
