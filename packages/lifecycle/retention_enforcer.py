"""§3.10.3 retention-floor enforcer. Implements PHASE_6_SPEC.md §6.4.

Loaded by the boot validator (validator 4 sub-check). Asserts the live
JSON config matches the Literal-pinned retention floors. Mismatch fails
boot with exit code 4 — production cannot run with relaxed retention.
"""

from __future__ import annotations

import json
from pathlib import Path

from packages.core.models.lifecycle import RetentionAssertion


class RetentionMismatch(AssertionError):
    """Raised when the live retention config drifts from the pinned floors."""


def load_retention_assertion(path: Path) -> RetentionAssertion:
    """Read and Pydantic-validate the retention config JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RetentionAssertion.model_validate(raw)


def assert_retention_floors(path: Path) -> RetentionAssertion:
    """Load + return the RetentionAssertion. Re-raise as RetentionMismatch.

    The Pydantic Literal pins do the floor enforcement; this wrapper exists
    so callers receive a domain-specific exception instead of a generic
    ValidationError when the config drifts.
    """
    try:
        return load_retention_assertion(path)
    except Exception as exc:
        raise RetentionMismatch(f"retention floors mismatched or missing in {path}: {exc}") from exc
