"""CLI: bulk-load un_locode_reference + carrier_port_aliases.

Implements PHASE_3_SPEC.md §5. Idempotent — TRUNCATE CASCADE before COPY.

Usage:
    python -m scripts.load_un_locode data/un_locode_2024_2.csv
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from packages.core.settings import get_settings
from packages.reference.loader import bulk_load_un_locode

_log = logging.getLogger(__name__)


def main() -> int:
    """Entry point. Returns 0 on success, non-zero on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv_path",
        type=Path,
        nargs="?",
        default=Path("data/un_locode_2024_2.csv"),
    )
    args = parser.parse_args()

    if not args.csv_path.exists():
        _log.error("csv not found: %s — run `python data/_generate.py` first", args.csv_path)
        return 2

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dsn = get_settings().postgres_dsn_async
    rows = asyncio.run(bulk_load_un_locode(dsn, args.csv_path))
    _log.info("loaded %d un_locode rows", rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
