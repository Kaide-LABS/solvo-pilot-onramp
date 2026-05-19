"""Retention-floor enforcer. PHASE_6_SPEC §8 criterion 8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.lifecycle.retention_enforcer import (
    RetentionMismatch,
    assert_retention_floors,
    load_retention_assertion,
)


def _write(tmp_path: Path, payload: dict[str, int]) -> Path:
    p = tmp_path / "retention.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_canonical_retention_floors_pass(tmp_path: Path) -> None:
    """The exact §3.10.3 values pass validation."""
    p = _write(
        tmp_path,
        {
            "raw_upload_retention_days": 7,
            "normalized_output_retention_days": 90,
            "archived_output_ttl_days": 180,
            "audit_log_retention_days": 365,
        },
    )
    cfg = load_retention_assertion(p)
    assert cfg.raw_upload_retention_days == 7
    assert cfg.normalized_output_retention_days == 90
    assert cfg.archived_output_ttl_days == 180
    assert cfg.audit_log_retention_days == 365


def test_relaxed_raw_upload_window_fails(tmp_path: Path) -> None:
    """30-day raw upload retention is rejected at the Pydantic Literal level."""
    p = _write(
        tmp_path,
        {
            "raw_upload_retention_days": 30,
            "normalized_output_retention_days": 90,
            "archived_output_ttl_days": 180,
            "audit_log_retention_days": 365,
        },
    )
    with pytest.raises(RetentionMismatch):
        assert_retention_floors(p)


def test_relaxed_audit_log_window_fails(tmp_path: Path) -> None:
    """365-day audit-log retention is the ISO 27001 floor — below it fails."""
    p = _write(
        tmp_path,
        {
            "raw_upload_retention_days": 7,
            "normalized_output_retention_days": 90,
            "archived_output_ttl_days": 180,
            "audit_log_retention_days": 30,
        },
    )
    with pytest.raises(RetentionMismatch):
        assert_retention_floors(p)


def test_extra_field_rejected(tmp_path: Path) -> None:
    """Unknown fields fail strict-forbid."""
    p = _write(
        tmp_path,
        {
            "raw_upload_retention_days": 7,
            "normalized_output_retention_days": 90,
            "archived_output_ttl_days": 180,
            "audit_log_retention_days": 365,
            "future_field": True,
        },
    )
    with pytest.raises(RetentionMismatch):
        assert_retention_floors(p)
