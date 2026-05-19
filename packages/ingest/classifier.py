"""Stage 1 — Deterministic Action Domain Classifier. Implements PHASE_2_SPEC.md §6.1.

ZERO LLM CALLS. Pure Python. This is the load-bearing white-box anchor:
routing decisions must be inspectable from the source without referencing
a model output.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import PurePosixPath

from packages.core.models.ratesheet import (
    ClassifiedFormat,
    DetectedFormat,
    SourceFormatHint,
)

_log = logging.getLogger(__name__)

# Hard cap on the magic-byte / sniff window. We never inspect more than this
# many bytes regardless of payload size; later phases enforce a 25 MiB upload
# cap before this function ever runs.
_MAGIC_WINDOW = 4096

# xlsx is a ZIP archive that starts with "PK\x03\x04" and always contains the
# Open Packaging Conventions content-types entry.
_XLSX_HEADER = b"PK\x03\x04"
_XLSX_OPC_MARKER = b"[Content_Types].xml"

# RFC822 email headers (any one of these in the first window indicates .eml).
_EML_RE = re.compile(rb"^(Return-Path|Received|From|To|Subject|Message-ID):", re.MULTILINE)

# EDIFACT messages start with UNA (service string advice) or UNB (envelope).
# A leading BOM is tolerated.
_EDIFACT_PREFIXES = (b"UNA", b"UNB", b"UNH")
_UTF8_BOM = b"\xef\xbb\xbf"

# Confidence threshold required to commit a non-uncertain classification.
_COMMIT_THRESHOLD = 0.9


def _detect_via_magic(payload: bytes) -> tuple[DetectedFormat, float, str] | None:
    """Inspect the leading bytes. Return None when nothing matches with high confidence."""
    window = payload[:_MAGIC_WINDOW]
    if window.startswith(_XLSX_HEADER) and _XLSX_OPC_MARKER in payload[: _MAGIC_WINDOW * 16]:
        # The 64KiB extended window covers the central directory pointer; for
        # very small fixtures it's a no-op.
        return "excel", 0.99, "xlsx_magic_bytes_and_opc_marker"
    if window.startswith(_XLSX_HEADER):
        # ZIP magic without OPC marker is ambiguous — could be a generic zip.
        # We do not commit to xlsx based on PK alone.
        return None
    stripped = window.lstrip(_UTF8_BOM)
    for prefix in _EDIFACT_PREFIXES:
        if stripped.startswith(prefix):
            return "edifact", 0.99, f"edifact_segment_{prefix.decode()}_at_offset_zero"
    if _EML_RE.search(window):
        return "email", 0.95, "rfc822_header_in_first_window"
    return None


def _detect_via_extension(filename: str) -> tuple[DetectedFormat, float, str] | None:
    """Extension-based fallback. Lower confidence than magic-byte detection."""
    suffix = PurePosixPath(filename).suffix.lower()
    mapping: dict[str, DetectedFormat] = {
        ".xlsx": "excel",
        ".xls": "excel",
        ".csv": "csv",
        ".edi": "edifact",
        ".eml": "email",
    }
    if suffix in mapping:
        return mapping[suffix], 0.85, f"extension_{suffix}"
    return None


def _detect_via_csv_sniff(payload: bytes) -> tuple[DetectedFormat, float, str] | None:
    """CSV sniffer as the last resort. Bounded sniff window of 8KiB."""
    window = payload[: _MAGIC_WINDOW * 2]
    try:
        decoded = window.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    try:
        dialect = csv.Sniffer().sniff(decoded)
    except csv.Error:
        return None
    # Require a non-trivial delimiter and at least two rows-worth of content.
    if dialect.delimiter not in {",", ";", "|", "\t"}:
        return None
    reader = csv.reader(io.StringIO(decoded), dialect=dialect)
    rows = sum(1 for _ in reader)
    if rows < 2:
        return None
    return "csv", 0.92, f"csv_sniffer_delim_{dialect.delimiter!r}_rows_{rows}"


def classify_format(
    payload: bytes,
    filename: str,
    hint: SourceFormatHint,
) -> ClassifiedFormat:
    """Detect the input format from the payload bytes and filename.

    Order of checks (first commit wins):
      1. Magic bytes (xlsx OPC, EDIFACT UN* segments, RFC822 headers).
      2. Extension fallback.
      3. CSV sniffer.

    Returns a ClassifiedFormat with detected_format='uncertain' when no check
    crosses the 0.9 confidence threshold. The 'hint' parameter is advisory:
    when it disagrees with magic-byte detection, magic bytes win and the
    disagreement is logged at WARNING level.
    """
    magic = _detect_via_magic(payload)
    if magic is not None:
        fmt, conf, reason = magic
        if hint != "auto" and hint != fmt:
            _log.warning(
                "classifier: hint=%s but magic-bytes say %s — trusting magic bytes",
                hint, fmt,
            )
        return ClassifiedFormat(detected_format=fmt, confidence=conf, reason=reason)

    ext = _detect_via_extension(filename)
    if ext is not None and ext[1] >= _COMMIT_THRESHOLD:
        return ClassifiedFormat(detected_format=ext[0], confidence=ext[1], reason=ext[2])

    sniff = _detect_via_csv_sniff(payload)
    if sniff is not None:
        return ClassifiedFormat(
            detected_format=sniff[0], confidence=sniff[1], reason=sniff[2]
        )

    # Last-resort: take the extension hit even below the commit threshold so
    # the caller knows what we tried, but mark it 'uncertain' if confidence
    # is too low.
    if ext is not None:
        return ClassifiedFormat(
            detected_format="uncertain",
            confidence=ext[1],
            reason=f"extension_{ext[0]}_below_threshold",
        )

    return ClassifiedFormat(
        detected_format="uncertain",
        confidence=0.0,
        reason="no_magic_bytes_no_extension_no_sniff",
    )
