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
import random
import string
from datetime import datetime
from itertools import product
from pathlib import Path

from openpyxl import Workbook

DATA_DIR = Path(__file__).parent
REPO_ROOT = DATA_DIR.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
TOTAL_UN_LOCODE_ROWS = 110_000
WCO_HS6_ROWS = 5_000

# Phase 6.5 (§6.2): deterministic RNG seed for the four demo fixtures.
DEMO_FIXTURE_SEED = 0x5010_06_2026
DEMO_FIXTURE_TIMESTAMP = datetime(2026, 5, 1, 0, 0, 0)

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


# ---------------------------------------------------------------------------
# Phase 6.5 (§6.2) — Demo fixtures: K+N Magic Moment + 3 broken inputs.
# ---------------------------------------------------------------------------

_CLEAN_PORTS: list[str] = [
    "DEHAM",
    "NLRTM",
    "BEANR",
    "GBFXT",
    "USNYC",
    "USLAX",
    "SGSIN",
    "HKHKG",
    "CNSHA",
    "NLAMS",
]
_OBFUSCATED_PORTS: list[str] = [
    "Hamburg DE",
    "Hambourg",
    "Rotterdam (NL)",
    "New York NY",
    "Antwerp",
    "Felixstowe UK",
    "Los Angeles",
    "Singapore",
    "Hong Kong",
    "Shanghai (CN)",
]
_EQUIPMENT_TYPES: list[str] = ["20DV", "40DV", "40HC", "40RF"]


def _pick_port(rng: random.Random) -> str:
    """Pick a port code with ~40/60 clean-vs-obfuscated ratio."""
    if rng.random() < 0.4:
        return rng.choice(_CLEAN_PORTS)
    return rng.choice(_OBFUSCATED_PORTS)


def _save_demo_workbook(wb: Workbook, name: str) -> None:
    """Save a workbook with deterministic timestamps + zip headers.

    openpyxl stamps the workbook's core properties at save time AND writes
    zip member entries with `time.time()` mtimes. To make the on-disk bytes
    byte-identical across re-runs we (a) pin the BaseModel-level created /
    modified properties and (b) rewrite the zip archive with a fixed
    `date_time` on every member entry.
    """
    import io
    import zipfile

    wb.properties.created = DEMO_FIXTURE_TIMESTAMP
    wb.properties.modified = DEMO_FIXTURE_TIMESTAMP
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    fixed_dt = (
        DEMO_FIXTURE_TIMESTAMP.year,
        DEMO_FIXTURE_TIMESTAMP.month,
        DEMO_FIXTURE_TIMESTAMP.day,
        DEMO_FIXTURE_TIMESTAMP.hour,
        DEMO_FIXTURE_TIMESTAMP.minute,
        DEMO_FIXTURE_TIMESTAMP.second,
    )
    out_path = FIXTURES_DIR / name
    pinned_iso = DEMO_FIXTURE_TIMESTAMP.strftime("%Y-%m-%dT%H:%M:%SZ")
    with (
        zipfile.ZipFile(buf, "r") as src,
        zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as dst,
    ):
        # Stable member ordering: sort by name so even Python dict-ordering
        # drift cannot perturb the resulting archive.
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            data = src.read(info.filename)
            # openpyxl re-stamps `dcterms:modified` to UTC-now during save(),
            # overriding the pinned wb.properties.modified assignment. Rewrite
            # the timestamp in-place so byte-identical re-runs are achievable.
            if info.filename == "docProps/core.xml":
                import re

                text = data.decode("utf-8")
                text = re.sub(
                    r"(<dcterms:modified[^>]*>)[^<]+(</dcterms:modified>)",
                    rf"\g<1>{pinned_iso}\g<2>",
                    text,
                )
                data = text.encode("utf-8")
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=fixed_dt)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            dst.writestr(new_info, data)


def _generate_kn_spot_rates() -> None:
    """Generate the 15-lane K+N Magic Moment fixture with 3 deliberate breakages.

    Phase 6.6 (§6.4.1) shrinks the fixture from 50 lanes to 15 to fit the
    recalibrated F.3.1 acceptance budget (180 s). Broken-lane positions
    moved from (23, 31, 47) to (7, 11, 14).

    Lane 7: origin_port = ZZZZZ (impossible UN/LOCODE — Stage 4 rejection).
    Lane 11: base_rate_usd = -1500.00 (negative — Stage 4 rejection).
    Lane 14: expiry_date = "Feb 1 2025" (past — Stage 4 flag).
    """
    rng = random.Random(DEMO_FIXTURE_SEED)  # noqa: S311 — fixture determinism only
    wb = Workbook()
    ws = wb.active
    ws.title = "Q2 2026 SPOT RATES"

    surcharge_cols = ["BAF", "CAF", "PSS", "GRI", "IMO", "War_Risk", "Document_Fee"]
    note_cols = [
        "carrier_note_1",
        "carrier_note_2",
        "carrier_note_3",
        "carrier_note_4",
        "carrier_note_5",
    ]
    header = [
        "origin_port",
        "destination_port",
        "equipment_type",
        "base_rate_usd",
        "effective_date",
        "expiry_date",
        *surcharge_cols,
        *note_cols,
    ]
    ws.append(header)

    # Phase 6.6: 3 merged-cell rate-tier header rows interleaved with the
    # 15-lane body (down from 5 tier rows for the 50-lane Phase 6.5 version).
    merged_at: dict[int, str] = {
        2: "STANDARD RATES",
        10: "SPOT RATES Q2 2026",
        16: "RF / TEMP-CONTROLLED",
    }

    sample_notes = [
        "Subject to availability, contact account exec for spot rate",
        "Free time per tariff; demurrage outside scope",
        "Acceptance subject to vessel space",
        "Hazardous goods require prior approval",
        "Rates exclude THC at origin",
    ]

    lane_idx = 1
    row_idx = 2  # ws.append already wrote header at row 1
    while lane_idx <= 15:
        if row_idx in merged_at:
            # Merge the entire row's columns under a tier label.
            label = merged_at[row_idx]
            ws.cell(row=row_idx, column=1, value=label)
            last_col_letter = ws.cell(row=row_idx, column=len(header)).column_letter
            ws.merge_cells(f"A{row_idx}:{last_col_letter}{row_idx}")
            row_idx += 1
            continue

        # Phase 6.6: Deliberate breakages moved to lanes (7, 11, 14).
        if lane_idx == 7:
            origin = "ZZZZZ"
        elif lane_idx == 11:
            origin = rng.choice(_CLEAN_PORTS)
        else:
            origin = _pick_port(rng)

        destination = _pick_port(rng)
        equipment = rng.choice(_EQUIPMENT_TYPES)

        if lane_idx == 11:
            rate = -1500.00
        else:
            rate = round(rng.uniform(800.0, 9500.0), 2)

        # Effective date: half ISO, half prose.
        if rng.random() < 0.5:
            effective = "2026-04-01"
        else:
            effective = rng.choice(["Apr 1 2026", "1 April 2026", "April 2026"])

        if lane_idx == 14:
            expiry = "Feb 1 2025"
        else:
            expiry = rng.choice(["2026-06-30", "Q2 2026", "Q3 2026", "30 June 2026", ""])

        surcharges = [
            round(rng.uniform(0.0, 450.0), 2) if rng.random() < 0.6 else "" for _ in surcharge_cols
        ]
        notes = [rng.choice(sample_notes) if rng.random() < 0.3 else "" for _ in note_cols]

        row_values = [
            origin,
            destination,
            equipment,
            rate,
            effective,
            expiry,
            *surcharges,
            *notes,
        ]
        for col_idx, value in enumerate(row_values, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)

        lane_idx += 1
        row_idx += 1

    _save_demo_workbook(wb, "K+N_Spot_Rates_Q2_2026_FINAL_v3.xlsx")


def _generate_broken_port_codes() -> None:
    """5 lanes; 2 trigger port_unknown_unlocode rejection."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["origin", "destination", "equipment", "base_rate_usd"])
    ws.append(["DEHAM", "USNYC", "40HC", 2100.0])
    ws.append(["NLRTM", "SGSIN", "40HC", 1850.0])
    ws.append(["ZZZZZ", "USLAX", "40HC", 2450.0])
    ws.append(["USLAX", "JPYOK", "20GP", 1750.0])
    ws.append(["DEHAM", "QQQQQ", "40HC", 2200.0])
    _save_demo_workbook(wb, "broken_impossible_port_codes.xlsx")


def _generate_broken_negative_rates() -> None:
    """4 lanes; 1 triggers negative_base_rate rejection."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["origin", "destination", "equipment", "base_rate_usd"])
    ws.append(["NLRTM", "USNYC", "40HC", 1850.0])
    ws.append(["DEHAM", "USLAX", "40HC", 2450.0])
    ws.append(["BEANR", "SGSIN", "40HC", 3100.0])
    ws.append(["GBFXT", "USNYC", "20GP", -2400.0])
    _save_demo_workbook(wb, "broken_negative_rates.xlsx")


def _generate_broken_edifact() -> None:
    """Valid PRICAT envelope with a corrupted UNH version qualifier."""
    content = (
        "UNB+UNOA:1+SENDER+RECIPIENT+260501:1200+1++PRICAT'"
        "UNH+1+PRICAT:D:01B:UN:EAN999'"
        "BGM+9+ORDER123+9'"
        "DTM+137:20260501:102'"
        "NAD+SU+SUPPLIER123++Sample Supplier'"
        "LIN+1++PRODUCT001:SA'"
        "PIA+5+12345:SA'"
        "IMD+F++:::SampleItem'"
        "QTY+1:100'"
        "PRI+AAA:1000:CT'"
        "UNS+S'"
        "CNT+2:1'"
        "UNT+11+1'"
        "UNZ+1+1'"
    )
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURES_DIR / "broken_malformed_edifact.edi").write_bytes(content.encode("ascii"))


def _generate_demo_fixtures() -> None:
    """Emit the four Phase 6.5 demo fixtures into fixtures/ deterministically."""
    _generate_kn_spot_rates()
    _generate_broken_port_codes()
    _generate_broken_negative_rates()
    _generate_broken_edifact()


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

    # Phase 6.5 (§6.2): emit the four demo fixtures alongside the reference CSVs.
    _generate_demo_fixtures()
    print("wrote 4 demo fixtures into fixtures/")


if __name__ == "__main__":
    main()
