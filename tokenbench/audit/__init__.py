"""Trace-aware exploit detection (Chunk 6 deliverable D).

Public API:
    from tokenbench.audit import scan_records, Finding, Severity
"""

from .exploit_detector import (
    Finding,
    Severity,
    scan_records,
    JUDGE_INJECTION_PATTERNS,
    GAMING_CONFIG_KEYS,
)

__all__ = [
    "Finding",
    "Severity",
    "scan_records",
    "JUDGE_INJECTION_PATTERNS",
    "GAMING_CONFIG_KEYS",
]
