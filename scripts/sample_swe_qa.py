"""Stratified SWE-QA sample for the Chunk 6 rigor sweep (deliverable C).

Reads the 210-task questions file and emits a stratified subsample to
`artifacts/swe_qa/v1.0.0/sample_chunk6.jsonl`. Strata are (repo_id,
difficulty) pairs; allocation follows the largest-remainder method to
mirror the full dataset's distribution as closely as possible at the
chosen sample size.

Frozen seed (default 1) so the sample is reproducible. Once committed
to git, the file IS the canonical Chunk 6 SWE-QA subset.

Usage:
    python scripts/sample_swe_qa.py --n 30 --seed 1
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def _largest_remainder(weights: dict[tuple[str, str], int], total: int
                       ) -> dict[tuple[str, str], int]:
    """Allocate `total` slots across strata proportional to `weights`.

    Each stratum gets floor(w_i / W * total); leftover slots go to the
    strata with the largest fractional remainder. Guarantees the sum is
    exactly `total` and that every stratum with weight > 0 gets at least
    its floor share.
    """
    W = sum(weights.values())
    if W == 0:
        return {k: 0 for k in weights}
    raw = {k: w / W * total for k, w in weights.items()}
    floor = {k: int(v) for k, v in raw.items()}
    leftover = total - sum(floor.values())
    if leftover > 0:
        # Largest fractional remainders take leftover slots first.
        ranked = sorted(
            weights.keys(),
            key=lambda k: (raw[k] - floor[k], weights[k]),
            reverse=True,
        )
        for k in ranked[:leftover]:
            floor[k] += 1
    return floor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30,
                    help="Sample size; default 30 (Chunk 6 scope F).")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--source",
        default="artifacts/swe_qa/v1.0.0/questions.jsonl",
        help="Full SWE-QA questions file.",
    )
    ap.add_argument(
        "--out",
        default="artifacts/swe_qa/v1.0.0/sample_chunk6.jsonl",
        help="Where to write the stratified subsample.",
    )
    args = ap.parse_args()

    src = Path(args.source)
    out = Path(args.out)
    rows = []
    for line in src.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    print(f"Loaded {len(rows)} questions from {src}")

    # Group by stratum (repo_id, difficulty)
    by_stratum: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        key = (r["repo_id"], r.get("difficulty", "none"))
        by_stratum[key].append(r)

    weights = {k: len(v) for k, v in by_stratum.items()}
    alloc = _largest_remainder(weights, args.n)

    rng = random.Random(args.seed)
    selected: list[dict] = []
    for stratum, k in sorted(alloc.items()):
        pool = by_stratum[stratum]
        if k == 0:
            continue
        # Sort pool by task_id for a deterministic ordering, then sample.
        pool_sorted = sorted(pool, key=lambda r: r["task_id"])
        picks = rng.sample(pool_sorted, k=min(k, len(pool_sorted)))
        selected.extend(picks)

    selected.sort(key=lambda r: r["task_id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        fh.write(f"# Chunk 6 deliverable C — stratified SWE-QA sample\n")
        fh.write(f"# n={args.n}  seed={args.seed}  source={src}\n")
        fh.write(f"# Allocation (repo, difficulty) → count:\n")
        for stratum in sorted(alloc):
            fh.write(f"#   {stratum}: {alloc[stratum]}\n")
        for r in selected:
            fh.write(json.dumps(r) + "\n")

    print(f"Wrote {len(selected)} tasks to {out}")
    print("\nStratum allocation:")
    for stratum in sorted(alloc):
        full = weights[stratum]
        a = alloc[stratum]
        print(f"  {stratum[0]:6s} {stratum[1]:7s}  {a:>2d} / {full:>3d} "
              f"({a/args.n*100:.1f}% sample vs {full/len(rows)*100:.1f}% full)")


if __name__ == "__main__":
    main()
