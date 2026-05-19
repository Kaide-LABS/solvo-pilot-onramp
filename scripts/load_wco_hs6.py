"""CLI: bulk-load wco_hs6_reference.

Implements PHASE_3_SPEC.md §5.

Usage:
    python -m scripts.load_wco_hs6 data/wco_hs6_2022.csv
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from packages.core.settings import get_settings
from packages.reference.loader import bulk_load_wco_hs6

_log = logging.getLogger(__name__)


def main() -> int:
    """Entry point. Returns 0 on success, non-zero on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        type=Path,
        nargs="?",
        default=Path("data/wco_hs6_2022.csv"),
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        _log.error("csv not found: %s — run `python data/_generate.py` first", args.csv_path)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dsn = get_settings().postgres_dsn_async
    rows = asyncio.run(bulk_load_wco_hs6(dsn, args.csv_path))
    _log.info("loaded %d wco_hs6 rows", rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
