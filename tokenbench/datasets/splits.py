"""Public / held-out 80-20 split (Chunk 6 deliverable E).

Implements DECISIONS.md #2:

  - 80% public / 20% held-out, stratified by language + repo size for
    needle (collapses to "by repo" since all 3 pinned repos are Python),
    and by repo × difficulty for SWE-QA.
  - Tasks are assigned at `dataset_version` freeze and never re-assigned.
  - Held-out manifest is never distributed with the dataset release —
    `artifacts/_heldout/` is gitignored.

Algorithm — deterministic largest-remainder allocation per stratum,
ordered by `task_id` lexicographic. NOT random: a random seed could be
"lost" or accidentally re-rolled; sorting + largest-remainder is fully
reproducible from the task list alone.

For each stratum (size N):
    held = round(N * 0.20)               # largest remainder rounding
    public = N - held
    sort tasks in the stratum by task_id ascending
    take the LAST `held` tasks as held-out, the rest as public

Why "last by task_id" rather than first or random: it's a stable,
documented choice that any reader can verify by inspection. Future
rotation (DECISIONS.md #7) just bumps the dataset_version and re-runs
this with the new task list — the algorithm itself doesn't change.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


HELDOUT_FRACTION = 0.20  # locked, DECISIONS.md #2


@dataclass(frozen=True)
class SplitAssignment:
    """One task's split assignment."""
    task_id: str
    split: str  # "public" or "heldout"
    stratum: tuple[str, ...]


def _heldout_count(stratum_size: int, fraction: float = HELDOUT_FRACTION) -> int:
    """Largest-remainder rounding for one stratum."""
    return int(round(stratum_size * fraction))


def assign_splits(
    items: Sequence[dict],
    *,
    stratum_keys: Sequence[str],
    fraction: float = HELDOUT_FRACTION,
) -> list[SplitAssignment]:
    """Assign each item in `items` to "public" or "heldout".

    `items` is any sequence of dicts with at least `task_id` plus the
    keys named in `stratum_keys`. Returns a list parallel to a stable
    sort of items by task_id.
    """
    by_stratum: dict[tuple, list[dict]] = defaultdict(list)
    for it in items:
        key = tuple(it[k] for k in stratum_keys)
        by_stratum[key].append(it)

    assignments: list[SplitAssignment] = []
    for stratum, group in by_stratum.items():
        group_sorted = sorted(group, key=lambda r: r["task_id"])
        n_held = _heldout_count(len(group_sorted), fraction=fraction)
        n_public = len(group_sorted) - n_held
        public = group_sorted[:n_public]
        held = group_sorted[n_public:]
        for it in public:
            assignments.append(SplitAssignment(
                task_id=it["task_id"], split="public", stratum=stratum,
            ))
        for it in held:
            assignments.append(SplitAssignment(
                task_id=it["task_id"], split="heldout", stratum=stratum,
            ))
    assignments.sort(key=lambda a: a.task_id)
    return assignments


def write_manifest(
    assignments: Iterable[SplitAssignment],
    *,
    public_path: Path,
    heldout_path: Path,
) -> tuple[int, int]:
    """Write public-only and heldout-only manifests as plain task_id lists.

    Returns (n_public, n_heldout).
    """
    public_path.parent.mkdir(parents=True, exist_ok=True)
    heldout_path.parent.mkdir(parents=True, exist_ok=True)
    public = [a for a in assignments if a.split == "public"]
    held = [a for a in assignments if a.split == "heldout"]
    with public_path.open("w") as fh:
        fh.write("# Public split — DECISIONS.md #2 (80%, stratified)\n")
        for a in public:
            fh.write(f"{a.task_id}\t{','.join(a.stratum)}\n")
    with heldout_path.open("w") as fh:
        fh.write("# HELD-OUT split — DECISIONS.md #2. NEVER DISTRIBUTE.\n")
        fh.write("# Stored under artifacts/_heldout/ which is gitignored.\n")
        for a in held:
            fh.write(f"{a.task_id}\t{','.join(a.stratum)}\n")
    return len(public), len(held)


def load_manifest(path: Path) -> set[str]:
    """Read a manifest file and return the set of task_ids it lists."""
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tid = line.split("\t", 1)[0]
        out.add(tid)
    return out
