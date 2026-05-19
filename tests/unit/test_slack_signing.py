"""Slack signature verification. PHASE_5_SPEC §8 criterion 2."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from packages.slack.signing import (
    REPLAY_WINDOW_SECONDS,
    SlackSignatureError,
    verify_signature,
)

_SECRET = "test-signing-secret"
_BODY = b"command=/solvo-onramp&text=status+abc"


def _signature(body: bytes, timestamp: str) -> str:
    digest = hmac.new(
        _SECRET.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    return f"v0={digest}"


def test_valid_signature_passes() -> None:
    ts = "1000"
    sig = _signature(_BODY, ts)
    assert (
        verify_signature(secret=_SECRET, body=_BODY, timestamp=ts, signature=sig, now=1000.0)
        is True
    )


def test_mismatched_signature_raises() -> None:
    with pytest.raises(SlackSignatureError, match="signature mismatch"):
        verify_signature(
            secret=_SECRET,
            body=_BODY,
            timestamp="1000",
            signature="v0=deadbeef" * 8,
            now=1000.0,
        )


def test_timestamp_outside_replay_window_raises() -> None:
    ts = "1000"
    sig = _signature(_BODY, ts)
    future = 1000.0 + REPLAY_WINDOW_SECONDS + 1
    with pytest.raises(SlackSignatureError, match="replay window"):
        verify_signature(secret=_SECRET, body=_BODY, timestamp=ts, signature=sig, now=future)


def test_empty_secret_rejected() -> None:
    with pytest.raises(SlackSignatureError, match="not configured"):
        verify_signature(secret="", body=_BODY, timestamp="1000", signature="v0=x", now=1000.0)
