"""Slack AsyncWebClient singleton. Implements PHASE_5_SPEC.md §1.

Only the outbox dispatcher should call this — request handlers MUST NOT.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.core.settings import Settings

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient


def get_slack_client(settings: Settings) -> AsyncWebClient:
    """Return an AsyncWebClient configured with the bot token.

    Phase 6.7-ops (Defect 11): per-call construction. The prior
    lru_cache(maxsize=1) keyed on Settings which is unhashable
    (Pydantic BaseSettings), so the dispatcher's `get_slack_client(settings)`
    raised `TypeError: unhashable type: 'Settings'` on every drain tick
    after Phase 6.6 first let the slack_post outbox row reach delivery.
    Mirrors the Phase 6.6 §6.2 per-call Vertex client pattern.
    """
    from slack_sdk.web.async_client import AsyncWebClient

    return AsyncWebClient(token=settings.slack_bot_token)
