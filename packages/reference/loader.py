"""Bulk-load helpers shared by the load_un_locode / load_wco_hs6 CLIs.

Implements PHASE_3_SPEC.md §5. Uses asyncpg's COPY pathway for the ≥100k-row
UN/LOCODE table. Idempotent: TRUNCATE CASCADE before COPY so re-runs land
the same row count.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import asyncpg

_log = logging.getLogger(__name__)


def _strip_jdbc_prefix(dsn: str) -> str:
    """Convert SQLAlchemy async-style DSN to a plain libpq URL."""
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn[len("postgresql+asyncpg://") :]
    if dsn.startswith("postgresql+psycopg2://"):
        return "postgresql://" + dsn[len("postgresql+psycopg2://") :]
    return dsn


def _stream_csv_rows(csv_path: Path, columns: list[str]) -> list[tuple[Any, ...]]:
    """Read the CSV into a list of column-ordered tuples for copy_records_to_table.

    The DictReader-then-tuple pattern keeps column order explicit and lets the
    caller see which columns the COPY expects without rewriting the schema.
    """
    rows: list[tuple[Any, ...]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV {csv_path.name} missing required columns: {sorted(missing)}")
        for raw in reader:
            rows.append(tuple(raw.get(c) or None for c in columns))
    return rows


async def bulk_load_un_locode(dsn: str, csv_path: Path) -> int:
    """Load un_locode_reference + carrier_port_aliases idempotently."""
    columns = [
        "code",
        "country_code",
        "place_name",
        "subdivision",
        "function",
        "latitude",
        "longitude",
    ]
    rows = _stream_csv_rows(csv_path, columns)
    conn = await asyncpg.connect(_strip_jdbc_prefix(dsn))
    try:
        async with conn.transaction():
            await conn.execute("TRUNCATE TABLE un_locode_reference CASCADE")
            await conn.copy_records_to_table(
                "un_locode_reference",
                records=rows,
                columns=columns,
            )
            # Seed the carrier alias table with the known fixture-related entries.
            aliases = [
                ("BSAS", "ARBUE", "carrier_alias_fixture"),
                ("NYC", "USNYC", "carrier_alias_fixture"),
                ("LA", "USLAX", "carrier_alias_fixture"),
                ("HKG", "HKHKG", "carrier_alias_fixture"),
                ("SHA", "CNSHA", "carrier_alias_fixture"),
            ]
            await conn.execute("TRUNCATE TABLE carrier_port_aliases")
            await conn.copy_records_to_table(
                "carrier_port_aliases",
                records=aliases,
                columns=["alias", "canonical", "source"],
            )
        _log.info("un_locode bulk load complete: %d rows", len(rows))
        return len(rows)
    finally:
        await conn.close()


async def bulk_load_wco_hs6(dsn: str, csv_path: Path) -> int:
    """Load wco_hs6_reference idempotently."""
    columns = ["hs6", "chapter", "heading", "description"]
    rows = _stream_csv_rows(csv_path, columns)
    conn = await asyncpg.connect(_strip_jdbc_prefix(dsn))
    try:
        async with conn.transaction():
            await conn.execute("TRUNCATE TABLE wco_hs6_reference")
            await conn.copy_records_to_table(
                "wco_hs6_reference",
                records=rows,
                columns=columns,
            )
        _log.info("wco_hs6 bulk load complete: %d rows", len(rows))
        return len(rows)
    finally:
        await conn.close()
