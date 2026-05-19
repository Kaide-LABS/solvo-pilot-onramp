"""Slash + mention dispatch. PHASE_5_SPEC §8."""

from __future__ import annotations

from typing import Any

import pytest

from packages.core.models.slack import SlackEventEnvelope, SlackSlashCommand
from packages.slack.handlers import handle_mention, handle_slash


def _cmd(text: str) -> SlackSlashCommand:
    return SlackSlashCommand(
        token="t",
        team_id="T",
        channel_id="C",
        user_id="U",
        command="/solvo-onramp",
        text=text,
        response_url="https://hooks.slack.com/x",
        trigger_id="1",
    )


@pytest.mark.asyncio
async def test_slash_status_with_job_id() -> None:
    out = await handle_slash(_cmd("status abc123"))
    assert out["response_type"] == "ephemeral"
    assert "abc123" in out["text"]


@pytest.mark.asyncio
async def test_slash_status_without_job_id_returns_usage() -> None:
    out = await handle_slash(_cmd("status"))
    assert "Usage" in out["text"]


@pytest.mark.asyncio
async def test_slash_upload_returns_instructions() -> None:
    out = await handle_slash(_cmd("upload"))
    assert "/v1/intake/jobs" in out["text"]


@pytest.mark.asyncio
async def test_slash_unknown_returns_help() -> None:
    out = await handle_slash(_cmd("nonsense"))
    assert "Solvo Onramp commands" in out["text"]


@pytest.mark.asyncio
async def test_mention_returns_help() -> None:
    event = SlackEventEnvelope(
        token="t",
        type="event_callback",
        event={"text": "<@onramp> help"},
    )
    out: dict[str, Any] = await handle_mention(event)
    assert "Solvo Onramp commands" in out["text"]
