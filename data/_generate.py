"""Deterministic generator for the Phase 3 reference-data CSVs.

Produces:
  data/un_locode_2024_2.csv  — 110,000 rows of synthetic UN/LOCODE-shaped data
                                including the real codes needed by the demo
                                fixtures (ARBUE, USNYC, USLAX, HKHKG, CNSHA,
                                NLRTM, DEHAM, BEANR, SGSIN, DEFRA, NLAMS,
                                GBLON, GBFXT, USNYC, USLAX).
  data/wco_hs6_2022.csv      — ~5,000 synthetic HS6 rows.

The generator is the audit trail. The CSVs themselves are gitignored because
the synthetic 110k-row UN/LOCODE file is ~9MB and would collide with the
project's pre-commit large-file gate. Re-running this script produces
byte-identical files when openpyxl/Python versions are stable.

Run from repo root:
    python data/_generate.py
"""

from __future__ import annotations

import csv
import string
from itertools import product
from pathlib import Path

DATA_DIR = Path(__file__).parent
TOTAL_UN_LOCODE_ROWS = 110_000
WCO_HS6_ROWS = 5_000

# Real codes the demo fixtures + carrier-alias seeds rely on. These land in
# the generated CSV first so they are present even if the synthetic generator
# would otherwise overwrite them.
_PINNED_REAL_CODES: list[tuple[str, str, str, str, str]] = [
    # (code, country, place, subdivision, function)
    ("ARBUE", "AR", "Buenos Aires", "C", "12345-78-"),
    ("USNYC", "US", "New York", "NY", "12345-78-"),
    ("USLAX", "US", "Los Angeles", "CA", "12345-78-"),
    ("HKHKG", "HK", "Hong Kong", "", "12345-78-"),
    ("CNSHA", "CN", "Shanghai", "", "12345-78-"),
    ("NLRTM", "NL", "Rotterdam", "", "12345-78-"),
    ("DEHAM", "DE", "Hamburg", "", "12345-78-"),
    ("BEANR", "BE", "Antwerp", "", "12345-78-"),
    ("SGSIN", "SG", "Singapore", "", "12345-78-"),
    ("DEFRA", "DE", "Frankfurt", "", "12345-78-"),
    ("NLAMS", "NL", "Amsterdam", "", "12345-78-"),
    ("GBLON", "GB", "London", "", "12345-78-"),
    ("GBFXT", "GB", "Felixstowe", "", "12345-78-"),
    ("MSP", "US", "Minneapolis-Saint Paul", "MN", "12345-78-"),
]


def _synthetic_un_locode_rows(count: int) -> list[tuple[str, str, str, str, str, str, str]]:
    """Generate `count` synthetic UN/LOCODE-shaped rows.

    Each code matches ^[A-Z]{2}[A-Z0-9]{3}$. Lat/lon are blank (canonical
    UN/LOCODE files frequently omit them for inland sites).
    """
    letters = string.ascii_uppercase
    alnum = letters + string.digits
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    # Country letters cycle through AA..ZZ; location cycles through three-char
    # alnum sequences. This produces 26*26*36^3 candidates; we only need 110k.
    iterator = product(letters, letters, alnum, alnum, alnum)
    for idx, (c1, c2, l1, l2, l3) in enumerate(iterator):
        if idx >= count:
            break
        code = f"{c1}{c2}{l1}{l2}{l3}"
        rows.append(
            (
                code,
                f"{c1}{c2}",
                f"Synthetic Locality {idx:06d}",
                "",
                "1-------",
                "",
                "",
            )
        )
    return rows


def _generate_un_locode(path: Path) -> None:
    """Write the un_locode CSV."""
    pinned = {row[0] for row in _PINNED_REAL_CODES}
    synthetic = [
        r
        for r in _synthetic_un_locode_rows(TOTAL_UN_LOCODE_ROWS + len(pinned))
        if r[0] not in pinned
    ][: TOTAL_UN_LOCODE_ROWS - len(_PINNED_REAL_CODES)]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "code",
                "country_code",
                "place_name",
                "subdivision",
                "function",
                "latitude",
                "longitude",
            ]
        )
        for code, country, place, sub, func in _PINNED_REAL_CODES:
            writer.writerow([code, country, place, sub, func, "", ""])
        for code, country, place, sub, func, lat, lon in synthetic:
            writer.writerow([code, country, place, sub, func, lat, lon])


def _generate_wco_hs6(path: Path) -> None:
    """Write the WCO HS6 CSV with WCO_HS6_ROWS deterministic entries."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["hs6", "chapter", "heading", "description"])
        for idx in range(WCO_HS6_ROWS):
            hs6 = f"{idx:06d}"
            chapter = hs6[:2]
            heading = hs6[:4]
            writer.writerow([hs6, chapter, heading, f"Synthetic commodity {hs6}"])


def main() -> None:
    """Generate both CSVs into the data/ directory.

    Phase 6 paranoia: refuses to run when ENVIRONMENT=production. Generator
    output is synthetic; production should be loaded from a vendored
    canonical UN/LOCODE snapshot, not from this script.
    """
    import os
    import sys

    if os.environ.get("ENVIRONMENT", "").lower() == "production":
        print(
            "refusing to generate synthetic data in production; "
            "load a vendored UN/LOCODE snapshot instead",
            file=sys.stderr,
        )
        sys.exit(2)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _generate_un_locode(DATA_DIR / "un_locode_2024_2.csv")
    _generate_wco_hs6(DATA_DIR / "wco_hs6_2022.csv")
    print(f"wrote un_locode_2024_2.csv ({TOTAL_UN_LOCODE_ROWS:,} rows)")
    print(f"wrote wco_hs6_2022.csv ({WCO_HS6_ROWS:,} rows)")


if __name__ == "__main__":
    main()
