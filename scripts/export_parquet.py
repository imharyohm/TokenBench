"""Export a JSONL results store to Parquet (Chunk 4 deliverable #4).

Parquet is a *derived* artefact, regenerable any time from the canonical
JSONL. We do not write to it from the runner; this script reads JSONL
through the SQLiteStore (so the mirror is current) and writes a Parquet
file alongside.

Usage:
    python scripts/export_parquet.py results/runs/chunk3.jsonl
    python scripts/export_parquet.py results/runs/chunk3.jsonl --out custom.parquet

Requires `pyarrow`. If it's not installed:
    pip install pyarrow

Falls back to a clear error message rather than silently writing CSV or
similar — Parquet is the spec, surface mismatches loudly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenbench.results.store import ResultsStore  # noqa: E402
from tokenbench.results.sqlite_store import SQLiteStore  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", help="Path to the JSONL results store")
    ap.add_argument("--out", default=None, help="Output parquet path (default: <jsonl>.parquet)")
    args = ap.parse_args(argv[1:])

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"missing: {jsonl_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else jsonl_path.with_suffix(".parquet")

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print(
            "pyarrow is required for Parquet export. Install with:\n"
            "    pip install pyarrow",
            file=sys.stderr,
        )
        return 2

    store = ResultsStore(jsonl_path)
    with SQLiteStore.from_jsonl(store) as mirror:
        rows = mirror.query()  # all rows
        if not rows:
            print(f"(empty store; wrote nothing)", file=sys.stderr)
            return 0

        # All rows share the same column set — build a column-oriented
        # dict from the list of dicts, hand to pyarrow.
        cols = list(rows[0].keys())
        table = pa.table({c: [r[c] for r in rows] for c in cols})
        pq.write_table(table, out_path)
        print(f"[ok] wrote {out_path}  ({len(rows)} rows, {len(cols)} cols)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
