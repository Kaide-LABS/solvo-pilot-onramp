"""Ingress request models. Implements PHASE_2_SPEC.md §3.1."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from packages.core.models.ratesheet import SourceFormatHint


class RatesheetIngressRequest(BaseModel):
    """Form-encoded fields accompanying the multipart file upload.

    The upload bytes themselves are NOT part of this model — FastAPI handles
    the file via UploadFile and the metadata via a parsed Form dependency.
    Strict-forbid keeps Solvo's "white-box" surface honest: unexpected
    metadata fields fail loud with 422.
    """

    model_config = ConfigDict(extra="forbid")

    prospect_id: str = Field(min_length=3, max_length=64)
    prospect_name: str = Field(min_length=2, max_length=128)
    source_format_hint: SourceFormatHint = "auto"
    requesting_user_slack_id: str = Field(min_length=2, max_length=64)
    callback_channel: str = Field(min_length=2, max_length=128)
