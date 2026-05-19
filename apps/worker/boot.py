"""Worker-side boot validator wiring. Implements PHASE_1_SPEC.md §8."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from celery.signals import worker_init

from packages.compliance.boot_validators import run_all_boot_validators
from packages.core.settings import get_settings


@worker_init.connect
def _validate_on_worker_init(**_kwargs: Any) -> None:
    """Mirror the API's boot validators on the Celery worker side.

    Exits with the first failure's exit code so the worker container refuses
    to enter the broker rotation when any compliance gate is broken.
    """
    results = asyncio.run(run_all_boot_validators(get_settings()))
    failed = [r for r in results if not r.passed]
    if failed:
        sys.exit(failed[0].exit_code_on_failure)
