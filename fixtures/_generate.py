"""Regenerate the five Phase 2 demo fixtures deterministically.

Run from repo root:  python fixtures/_generate.py

Re-runnable. Produces byte-identical files given the same openpyxl version,
which keeps git diffs sane when fixtures are committed.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).parent


def _save(wb: Workbook, name: str) -> None:
    path = FIXTURES_DIR / name
    wb.save(path)


def _clean() -> None:
    """01 — baseline well-formed ratesheet, three lanes, USD."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(
        [
            "origin",
            "destination",
            "equipment",
            "base_rate_usd",
            "validity_start",
            "validity_end",
        ]
    )
    ws.append(["NLRTM", "USNYC", "40HC", 2100, date(2026, 1, 1), date(2026, 6, 30)])
    ws.append(["DEHAM", "USLAX", "40HC", 2450, date(2026, 1, 1), date(2026, 6, 30)])
    ws.append(["BEANR", "SGSIN", "40HC", 1850, date(2026, 1, 1), date(2026, 6, 30)])
    _save(wb, "01_clean_excel.xlsx")


def _merged() -> None:
    """02 — merged origin/destination cells across a two-row header block."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.merge_cells("A1:B1")
    ws["A1"] = "Lane"
    ws.merge_cells("C1:D1")
    ws["C1"] = "Commercial"
    ws.append(["origin", "destination", "equipment", "base_rate_usd"])
    ws.append(["NLRTM", "USNYC", "40HC", 2100])
    ws.append(["DEHAM", "USLAX", "20GP", 1200])
    _save(wb, "02_merged_cells.xlsx")


def _obfuscated() -> None:
    """03 — carrier-internal port codes (BSAS for ARBUE etc.); Phase 3 resolves them."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["origin_code", "destination_code", "equipment", "base_rate_usd"])
    ws.append(["BSAS", "MSP", "40HC", 3100])
    ws.append(["NYC", "HKG", "40HC", 2750])
    ws.append(["LAX", "SHA", "20GP", 1850])
    _save(wb, "03_obfuscated_ports.xlsx")


def _mixed_currencies() -> None:
    """04 — currency column varies across rows; extractor preserves raw values."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["origin", "destination", "equipment", "base_rate", "currency"])
    ws.append(["NLRTM", "USNYC", "40HC", 2100, "USD"])
    ws.append(["DEHAM", "USLAX", "40HC", 2200, "EUR"])
    ws.append(["GBFXT", "USNYC", "40HC", 1900, "GBP"])
    _save(wb, "04_mixed_currencies.xlsx")


def _mixed_units() -> None:
    """05 — surcharge unit basis varies (per container vs per shipment)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(
        [
            "origin",
            "destination",
            "equipment",
            "base_rate_usd",
            "surcharge_code",
            "surcharge_amount",
            "surcharge_basis",
        ]
    )
    ws.append(["NLRTM", "USNYC", "40HC", 2100, "BAF", 350, "per_container"])
    ws.append(["DEHAM", "USLAX", "40HC", 2450, "DOC", 50, "per_shipment"])
    _save(wb, "05_mixed_units.xlsx")


def main() -> None:
    _clean()
    _merged()
    _obfuscated()
    _mixed_currencies()
    _mixed_units()


if __name__ == "__main__":
    main()
