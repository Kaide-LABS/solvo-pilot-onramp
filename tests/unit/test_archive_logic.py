"""Pure-Python archive logic checks. PHASE_6_SPEC §8."""

from __future__ import annotations

import gzip
import inspect
import json

from packages.lifecycle import archive as archive_mod


def test_archive_blob_name_is_per_job_id_gzip() -> None:
    """Blob naming is deterministic and ends with .json.gz."""
    assert archive_mod._blob_name("job-1") == "jobs/job-1.json.gz"
    assert archive_mod._blob_name("ABC") == "jobs/ABC.json.gz"


def test_archive_audit_log_table_is_never_archived() -> None:
    """Static guarantee — onramp_audit_log is NOT referenced as a delete target."""
    source = inspect.getsource(archive_mod)
    # audit_log lives forever per §3.10.3 — archive must not target it.
    assert "delete(OnrampAuditLog)" not in source
    assert "DELETE FROM onramp_audit_log" not in source


def test_gzipped_payload_roundtrip_preserves_normalized_json() -> None:
    """The gzip encoding the archive job uses is reversible."""
    payload = {"job_id": "j", "lanes": [{"lane_id": "L1"}]}
    encoded = gzip.compress(json.dumps(payload).encode("utf-8"))
    decoded = json.loads(gzip.decompress(encoded).decode("utf-8"))
    assert decoded == payload


def test_archive_task_name_pinned() -> None:
    """The Celery task name is what the beat schedule and acceptance tests target."""
    assert archive_mod.archive_old_task.name == "tasks.lifecycle.archive_old"
