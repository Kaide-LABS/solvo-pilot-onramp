"""Slash-command + mention dispatch. Implements PHASE_5_SPEC.md §6.6.

These handlers return plain ephemeral response payloads. They do NOT call
Slack directly — all outbound Slack traffic flows through the outbox
dispatcher.
"""

from __future__ import annotations

from typing import Any

from packages.core.models.slack import SlackEventEnvelope, SlackSlashCommand

_HELP_TEXT = (
    "Solvo Onramp commands:\n"
    "• `/solvo-onramp status <job_id>` — query a job's pipeline status.\n"
    "• `/solvo-onramp upload` — instructions for submitting a ratesheet.\n"
    "Mention `@solvo-onramp help` for this message in-channel."
)

_UPLOAD_INSTRUCTIONS = (
    "Submit ratesheets via POST `/v1/intake/jobs` with multipart/form-data. "
    "Slack file uploads are not yet supported."
)


async def handle_slash(cmd: SlackSlashCommand) -> dict[str, Any]:
    """Dispatch a /solvo-onramp slash command to the right handler."""
    args = cmd.text.split()
    if not args:
        return {"response_type": "ephemeral", "text": _HELP_TEXT}

    sub = args[0].lower()
    if sub == "status":
        if len(args) < 2:
            return {
                "response_type": "ephemeral",
                "text": "Usage: `/solvo-onramp status <job_id>`",
            }
        job_id = args[1]
        return {
            "response_type": "ephemeral",
            "text": f"Looking up job `{job_id}`. Result will arrive in this channel.",
        }
    if sub == "upload":
        return {"response_type": "ephemeral", "text": _UPLOAD_INSTRUCTIONS}
    return {"response_type": "ephemeral", "text": _HELP_TEXT}


async def handle_mention(event: SlackEventEnvelope) -> dict[str, Any]:
    """Dispatch a Slack mention event. Phase 5 only handles 'help'."""
    event_data = event.event or {}
    text = (event_data.get("text") or "").lower()
    if "help" in text:
        return {"response_type": "in_channel", "text": _HELP_TEXT}
    return {"response_type": "in_channel", "text": _HELP_TEXT}
