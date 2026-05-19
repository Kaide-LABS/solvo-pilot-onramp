"""Placeholder so the import graph is stable across Phases 1–4.

This file is replaced in Phase 2 by the deterministic Stage 1 classifier and
Stage 2 extractor modules. Importing anything from it in Phase 1 is an error.
"""

from __future__ import annotations


def _phase1_placeholder() -> None:
    """Raised on any accidental Phase-1 reference to ingest pipeline code."""
    raise NotImplementedError(
        "Ingest pipeline is not implemented in Phase 1; see PHASE_1_SPEC §10."
    )
