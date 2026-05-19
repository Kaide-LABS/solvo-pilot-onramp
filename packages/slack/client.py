"""Slack AsyncWebClient singleton. Implements PHASE_5_SPEC.md §1.

Only the outbox dispatcher should call this — request handlers MUST NOT.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from packages.core.settings import Settings

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient


@lru_cache(maxsize=1)
def get_slack_client(settings: Settings) -> AsyncWebClient:
    """Return a cached AsyncWebClient configured with the bot token."""
    from slack_sdk.web.async_client import AsyncWebClient

    return AsyncWebClient(token=settings.slack_bot_token)
