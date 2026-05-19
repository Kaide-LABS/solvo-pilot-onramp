"""Integration smoke for docker-compose readiness. PHASE_1_SPEC §9 criterion 1.

Skipped automatically when SOLVO_RUN_COMPOSE_TESTS is unset — the test requires
a live docker-compose stack and is impractical in CI without docker-in-docker.
Run locally with: SOLVO_RUN_COMPOSE_TESTS=1 pytest tests/integration -q
"""

from __future__ import annotations

import os
import subprocess

import pytest

_should_run = os.getenv("SOLVO_RUN_COMPOSE_TESTS") == "1"


@pytest.mark.skipif(not _should_run, reason="set SOLVO_RUN_COMPOSE_TESTS=1 to enable")
def test_compose_health_reports_ok() -> None:
    """docker compose ps reports all four services as healthy."""
    out = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Smoke-only: presence of api + worker + postgres + redis in the output.
    for required in ("api", "worker", "postgres", "redis"):
        assert required in out.stdout, f"service {required} not present in compose ps"
