"""CLI: run the trace-aware exploit detector over a results store.

Usage:
    python scripts/audit_runs.py [--records PATH ...] [--claims-zero-context P ...]

Exits non-zero if any HIGH-severity findings are reported. Intended for
the leaderboard publishing flow (Chunk 6 exit gate 3): no top-N
submission ships if a HIGH finding is open.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tokenbench.audit import Finding, Severity, scan_records
from tokenbench.results.store import ResultsStore

DEFAULT_RECORDS = [
    "results/runs/chunk3.jsonl",
    "results/runs/chunk6_baselines.jsonl",
]


def _load(paths: list[str]):
    out = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"  (skip: {p} not present)")
            continue
        recs = list(ResultsStore(path).all())
        print(f"  loaded {len(recs):4d} records from {p}")
        out.extend(recs)
    return out


def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("\nNo findings. Audit clean.")
        return
    by_sev: dict[Severity, list[Finding]] = {s: [] for s in Severity}
    for f in findings:
        by_sev[f.severity].append(f)

    for sev in (Severity.HIGH, Severity.MEDIUM, Severity.LOW):
        bucket = by_sev[sev]
        if not bucket:
            continue
        print(f"\n=== {sev.value.upper()} ({len(bucket)}) ===")
        for f in bucket:
            print(f"  {f.short()}")
            if f.evidence:
                print(f"        evidence: {f.evidence}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", nargs="*", default=DEFAULT_RECORDS,
                    help="JSONL run-record stores to audit.")
    ap.add_argument(
        "--claims-zero-context", nargs="*", default=[],
        help=("Provider names that submitted as priors-only / no retrieval. "
              "C3 (priors-floor anomaly) only fires against these."),
    )
    ap.add_argument("--tolerance", type=float, default=0.20,
                    help="Δacc tolerance for the priors-floor anomaly.")
    args = ap.parse_args()

    print("Loading records:")
    records = _load(args.records)
    if not records:
        print("Nothing to audit.")
        return 0

    findings = scan_records(
        records,
        claims_zero_context=args.claims_zero_context,
        tolerance=args.tolerance,
    )
    _print_findings(findings)
    high_count = sum(1 for f in findings if f.severity == Severity.HIGH)
    if high_count:
        print(f"\nExit: {high_count} HIGH finding(s) — publication gate FAIL.")
        return 1
    print("\nExit: no HIGH findings — publication gate PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
