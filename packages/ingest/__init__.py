"""Ingest pipeline package. Implements PHASE_2_SPEC.md §1.

Public surface re-exports for Stage 1 + Stage 2. Later phases extend this
package with normalize/validate stages and EDIFACT support without changing
the existing exports.
"""

from packages.ingest.classifier import classify_format
from packages.ingest.excel_extractor import (
    ExcelTooLargeError,
    ExtractionError,
    extract_excel_payload,
)
from packages.ingest.outbox import enqueue_outbox_event

__all__ = [
    "ExcelTooLargeError",
    "ExtractionError",
    "classify_format",
    "enqueue_outbox_event",
    "extract_excel_payload",
]
