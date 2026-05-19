"""Block Kit summary builder. Implements PHASE_5_SPEC.md §6.2.

Anti-Replication invariant: the summary NEVER embeds raw rate values,
surcharge amounts, or any monetary figure. Only counts, flagged reasons,
and the signed-URL link.
"""

from __future__ import annotations

from typing import Any, Final

from packages.core.models.ratesheet import NormalizedRatesheet

_MAX_FLAGGED_REASONS_SHOWN: Final[int] = 3


def build_summary_blocks(
    *,
    rs: NormalizedRatesheet,
    signed_url: str,
    expires_at_iso: str,
) -> list[dict[str, Any]]:
    """Render a Block Kit message summarizing the ratesheet result.

    The blocks list contains:
      - a header with the prospect_id
      - a section with three counts (validated, flagged, rejected)
      - a context with the first three flagged reasons (deduplicated)
      - a section with the signed-URL link + expiry
    """
    validated_count = len(rs.lanes)
    flagged_count = len(rs.flagged_for_review)
    rejected_count = len(rs.deterministically_rejected)

    # Deduplicate reasons while preserving order.
    seen: set[str] = set()
    flagged_reasons: list[str] = []
    for fl in rs.flagged_for_review:
        if fl.reason in seen:
            continue
        seen.add(fl.reason)
        flagged_reasons.append(fl.reason)
        if len(flagged_reasons) >= _MAX_FLAGGED_REASONS_SHOWN:
            break

    reason_summary = ", ".join(flagged_reasons) if flagged_reasons else "no flags"

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Onramp result — {rs.prospect_id}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Validated lanes*\n{validated_count}"},
                {"type": "mrkdwn", "text": f"*Flagged*\n{flagged_count}"},
                {"type": "mrkdwn", "text": f"*Rejected*\n{rejected_count}"},
                {"type": "mrkdwn", "text": f"*Job*\n`{rs.job_id}`"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Flagged reasons: {reason_summary}"}],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{signed_url}|Download normalized JSON> — expires {expires_at_iso}",
            },
        },
    ]
