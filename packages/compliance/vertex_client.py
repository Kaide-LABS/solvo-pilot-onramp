"""Vertex AI client factory. Implements PHASE_1_SPEC.md §7.1.

Region binding to europe-west4 is non-negotiable. Settings.vertex_location is
Literal["europe-west4"] so substitution attempts fail at validation time, before
this factory is ever called.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from packages.core.settings import Settings

if TYPE_CHECKING:
    from google.genai import Client


@lru_cache(maxsize=1)
def get_vertex_client(settings: Settings) -> Client:
    """Return a singleton Vertex AI client bound to europe-west4.

    The lru_cache ensures we open the gRPC channel exactly once per process.
    """
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_location,
    )
