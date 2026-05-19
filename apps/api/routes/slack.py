"""Slack Events + slash + mention webhook. Implements PHASE_5_SPEC.md §4.1.

Signature verification runs BEFORE body parsing — no untrusted bytes reach
the Pydantic validators until HMAC + replay-window checks pass.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from packages.core.models.slack import SlackEventEnvelope, SlackSlashCommand
from packages.core.settings import Settings, get_settings
from packages.slack.handlers import handle_mention, handle_slash
from packages.slack.signing import SlackSignatureError, verify_signature

router = APIRouter()


@router.post(
    "",
    responses={
        200: {"description": "ok"},
        401: {"description": "signature_mismatch"},
        403: {"description": "replay_window_exceeded"},
        422: {"description": "validation_error"},
    },
)
async def slack_webhook(
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Verify HMAC, then dispatch by content-type / body type."""
    body = await request.body()
    try:
        verify_signature(
            secret=settings.slack_signing_secret,
            body=body,
            timestamp=x_slack_request_timestamp,
            signature=x_slack_signature,
        )
    except SlackSignatureError as exc:
        msg = str(exc)
        code = status.HTTP_403_FORBIDDEN if "replay window" in msg else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(status_code=code, detail=msg) from exc

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/x-www-form-urlencoded"):
        form = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items() if v}
        try:
            cmd = SlackSlashCommand.model_validate(form)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        result = await handle_slash(cmd)
        return JSONResponse(content=result)

    if content_type.startswith("application/json"):
        import json

        envelope_raw = json.loads(body)
        try:
            envelope = SlackEventEnvelope.model_validate(envelope_raw)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        if envelope.type == "url_verification":
            return JSONResponse(content={"challenge": envelope.challenge or ""})
        if envelope.type == "event_callback":
            result = await handle_mention(envelope)
            return JSONResponse(content=result)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="unsupported content-type or body",
    )
