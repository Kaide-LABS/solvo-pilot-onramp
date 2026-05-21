"""Vertex AI client factory. Implements PHASE_1_SPEC.md §7.1.

Region binding to europe-west4 is non-negotiable. Settings.vertex_location is
Literal["europe-west4"] so substitution attempts fail at validation time, before
this factory is ever called.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.core.settings import Settings

if TYPE_CHECKING:
    from google.genai import Client

# Module-level singleton. Settings is not hashable so lru_cache(settings) raises
# TypeError; we cache by gcp_project_id + vertex_location instead.
_client_cache: dict[tuple[str, str], Client] = {}


def get_vertex_client(settings: Settings) -> Client:
    """Return a singleton Vertex AI client bound to europe-west4.

    Caches by (project, location) so the gRPC channel opens at most once per
    distinct configuration. Settings (Pydantic BaseSettings) is unhashable so
    we cannot use lru_cache directly.
    """
    key = (settings.gcp_project_id, settings.vertex_location)
    client = _client_cache.get(key)
    if client is None:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
        _client_cache[key] = client
    return client
