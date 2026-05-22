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

def get_vertex_client(settings: Settings) -> Client:
    """Construct a fresh Vertex AI client bound to the configured location.

    NOT cached. The genai Client wraps an httpx AsyncClient whose connections
    are bound to the asyncio loop that opens them. Under Celery's prefork +
    `asyncio.run`-per-task model — same Defect-1 vector as the SQLAlchemy
    engine fix in PHASE_6_5_SPEC §6.1 — a module-level cache lets a child
    process inherit a client whose pooled connections reference the parent's
    (closed) boot-validator loop, surfacing as `Event loop is closed` on the
    first task call. Per-call construction avoids the cross-loop hazard.
    """
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.vertex_location,
    )
