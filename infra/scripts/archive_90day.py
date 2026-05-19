"""Manual archive sweep helper. Implements PHASE_6_SPEC.md §1.

The production cadence runs as a Celery beat task (`tasks.lifecycle.archive_old`).
This script lets ops trigger a sweep ad hoc from a one-off Cloud Run Job.

Usage:
    python infra/scripts/archive_90day.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from packages.core.settings import get_settings
from packages.lifecycle.archive import archive_completed_jobs


def main() -> int:
    """Run one archive sweep against the live config."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    candidates = asyncio.run(
        archive_completed_jobs(age_days=settings.archive_age_days, settings=settings)
    )
    print(f"archived {len(candidates)} jobs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
