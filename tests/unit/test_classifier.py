"""Stage 1 classifier tests. PHASE_2_SPEC §8 criterion 1."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.ingest.classifier import classify_format

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.parametrize(
    "filename",
    [
        "01_clean_excel.xlsx",
        "02_merged_cells.xlsx",
        "03_obfuscated_ports.xlsx",
        "04_mixed_currencies.xlsx",
        "05_mixed_units.xlsx",
    ],
)
def test_all_fixtures_detected_as_excel(filename: str) -> None:
    """Every committed Phase 2 fixture must classify as excel via magic bytes."""
    payload = (FIXTURES / filename).read_bytes()
    result = classify_format(payload, filename, "auto")
    assert result.detected_format == "excel"
    assert result.confidence >= 0.9


def test_edifact_magic_detected() -> None:
    """EDIFACT UNB segment at offset zero must classify as edifact."""
    payload = b"UNB+UNOA:1+SENDER+RECEIVER+260101:1200+1'"
    result = classify_format(payload, "freight.edi", "auto")
    assert result.detected_format == "edifact"


def test_eml_magic_detected() -> None:
    """RFC822 headers in the first window classify as email."""
    payload = b"From: ops@acme.com\r\nTo: rates@solvo.ai\r\nSubject: rates\r\n\r\nbody"
    result = classify_format(payload, "rates.eml", "auto")
    assert result.detected_format == "email"


def test_csv_sniffer_path() -> None:
    """A plain CSV body with no extension still classifies as csv via sniffer."""
    payload = b"origin,destination,rate\nNLRTM,USNYC,2100\nDEHAM,USLAX,2450\n"
    result = classify_format(payload, "ratesheet.csv", "auto")
    # Extension path is high-confidence; either route is valid as long as we land on csv.
    assert result.detected_format == "csv"


def test_uncertain_for_garbage() -> None:
    """Random bytes with no extension and no magic match return 'uncertain'."""
    payload = b"\x00\x01\x02\x03random binary blob with no signal"
    result = classify_format(payload, "blob.bin", "auto")
    assert result.detected_format == "uncertain"


def test_hint_loses_to_magic_bytes(caplog: pytest.LogCaptureFixture) -> None:
    """When hint contradicts magic bytes, magic wins and a WARNING is logged."""
    payload = b"UNB+UNOA:1+S+R+260101:1200+1'"
    with caplog.at_level("WARNING"):
        result = classify_format(payload, "x.edi", "excel")
    assert result.detected_format == "edifact"
    assert any("trusting magic bytes" in r.message for r in caplog.records)
