"""Outbox dispatcher static guarantees. PHASE_5_SPEC §8 criterion 6."""

from __future__ import annotations

from packages.dispatcher.outbox_worker import (
    BACKOFF_SCHEDULE_SECONDS,
    MAX_ATTEMPTS,
    backoff_for,
)


def test_exponential_backoff_schedule_pinned() -> None:
    """The schedule mirrors PHASE_5_SPEC §6.4: 5s → 30s → 5m → 30m → 2h → 24h."""
    assert BACKOFF_SCHEDULE_SECONDS == (5, 30, 300, 1800, 7200, 86400)
    assert MAX_ATTEMPTS == 6


def test_backoff_for_returns_correct_delays() -> None:
    assert backoff_for(0) == 5
    assert backoff_for(1) == 30
    assert backoff_for(2) == 300
    assert backoff_for(3) == 1800
    assert backoff_for(4) == 7200
    assert backoff_for(5) == 86400


def test_backoff_for_returns_none_after_max_attempts() -> None:
    """At MAX_ATTEMPTS and beyond, the dispatcher stops scheduling retries."""
    assert backoff_for(MAX_ATTEMPTS) is None
    assert backoff_for(MAX_ATTEMPTS + 5) is None


def test_lock_pattern_is_set_nx_ex() -> None:
    """Static check: the lock acquisition uses SET NX EX, not Redlock / WATCH+MULTI."""
    import inspect

    from packages.dispatcher import outbox_worker

    source = inspect.getsource(outbox_worker)
    assert "client.set(" in source
    assert "nx=True" in source
    assert "ex=" in source
    # Negative guarantees.
    assert "Redlock" not in source
    assert "WATCH" not in source
    assert "MULTI" not in source
