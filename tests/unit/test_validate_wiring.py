"""Phase 4 wiring carry-forward — PHASE_5_SPEC §7.1 + §8 criterion 7.

Verifies that validate_output_task imports and calls conformal,
conditional_correction, and draft_clarification — not just rules_engine.
"""

from __future__ import annotations

import inspect

from packages.ingest import tasks as tasks_mod


def test_validate_calls_conformal_correction_and_clarification() -> None:
    """The _validate body references each carry-forward module by symbol."""
    source = inspect.getsource(tasks_mod._validate)
    assert "compute_conformal_score" in source
    assert "conditional_correction" in source
    assert "draft_clarification" in source
    assert "load_calibration" in source


def test_validate_writes_completed_status() -> None:
    """The terminal `completed` transition lives in _validate, not normalize."""
    source = inspect.getsource(tasks_mod._validate)
    assert 'new_status="completed"' in source
    assert "completed=True" in source


def test_validate_emits_validated_audit_log() -> None:
    """The validate stage emits an audit_log row with stage='validated'."""
    source = inspect.getsource(tasks_mod._validate)
    assert 'event_type="audit_log"' in source
    assert '"validated"' in source
    # And it includes the conformal_summary metadata (the Phase 5 carry-forward signal).
    assert "conformal_summary" in source
    assert "correction_triggered" in source
    assert "clarifications" in source


def test_normalize_persists_consensus_votes_for_validate() -> None:
    """Phase 5 wiring: _normalize calls _persist_consensus_votes."""
    source = inspect.getsource(tasks_mod._normalize)
    assert "_persist_consensus_votes" in source
