"""Slack request models. Implements PHASE_5_SPEC.md §3.2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SlackSlashCommand(BaseModel):
    """Slack slash-command form-encoded body."""

    model_config = ConfigDict(extra="forbid")

    token: str
    team_id: str
    channel_id: str
    user_id: str
    command: Literal["/solvo-onramp"]
    text: str = Field(default="", max_length=512)
    response_url: str = Field(min_length=8, max_length=512)
    trigger_id: str


class SlackEventEnvelope(BaseModel):
    """Slack Events API envelope (mention + url_verification)."""

    model_config = ConfigDict(extra="forbid")

    token: str
    team_id: str | None = None
    api_app_id: str | None = None
    type: Literal["event_callback", "url_verification"]
    challenge: str | None = None
    event: dict[str, Any] | None = None


class SlackPostResult(BaseModel):
    """Slack post acknowledgement persisted into the outbox payload."""

    model_config = ConfigDict(extra="forbid")

    channel: str
    ts: str
    job_id: str
    posted_at: datetime
