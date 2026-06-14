"""Freeze the public / held-out 80-20 split for v1.0.0 datasets.

Per DECISIONS.md #2:
  - needle: stratified by repo (== language since all 3 pins are Python).
  - swe-qa: stratified by repo × difficulty.
  - 20% held-out, "last-by-task_id-within-stratum" — fully deterministic
    and inspectable from the task list alone (no random seed).

Outputs:
  - artifacts/needle/v1.0.0/public_split.tsv         tracked
  - artifacts/_heldout/needle/v1.0.0/heldout_split.tsv   gitignored
  - artifacts/swe_qa/v1.0.0/public_split.tsv         tracked
  - artifacts/_heldout/swe_qa/v1.0.0/heldout_split.tsv   gitignored

Run once at dataset_version freeze. After v1.0.0 these manifests ARE
the split — re-running this script must produce the same files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.datasets.splits import (
    HELDOUT_FRACTION,
    assign_splits,
    write_manifest,
)
from tokenbench.datasets.swe_qa import SweQaDataset

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

NEEDLE_PUBLIC = _PROJECT_ROOT / "artifacts" / "needle" / "v1.0.0" / "public_split.tsv"
NEEDLE_HELD = _PROJECT_ROOT / "artifacts" / "_heldout" / "needle" / "v1.0.0" / "heldout_split.tsv"
SWE_QA_PUBLIC = _PROJECT_ROOT / "artifacts" / "swe_qa" / "v1.0.0" / "public_split.tsv"
SWE_QA_HELD = _PROJECT_ROOT / "artifacts" / "_heldout" / "swe_qa" / "v1.0.0" / "heldout_split.tsv"


def _freeze_needle(max_per_repo: int) -> None:
    ds = NeedleCodebaseDataset(max_tasks_per_repo=max_per_repo)
    items = []
    for t in ds.tasks():
        items.append({
            "task_id": t.task_id,
            "repo": t.meta.get("repo_id", "?"),
            "language": t.meta.get("language", "?"),
        })
    print(f"\nneedle: {len(items)} tasks (max_tasks_per_repo={max_per_repo})")
    # Stratify by (language, repo). All Python here, but keep both keys
    # so a future cross-language extension just adds strata.
    assigns = assign_splits(items, stratum_keys=("language", "repo"))
    n_pub, n_held = write_manifest(
        assigns, public_path=NEEDLE_PUBLIC, heldout_path=NEEDLE_HELD,
    )
    print(f"  public:  {n_pub:3d} → {NEEDLE_PUBLIC.relative_to(_PROJECT_ROOT)}")
    print(f"  heldout: {n_held:3d} → {NEEDLE_HELD.relative_to(_PROJECT_ROOT)}")
    _print_strata("needle", assigns)


def _freeze_swe_qa() -> None:
    ds = SweQaDataset()
    items = []
    for t in ds.tasks():
        items.append({
            "task_id": t.task_id,
            "repo": t.meta.get("repo_id", "?"),
            "difficulty": t.meta.get("difficulty", "none"),
        })
    print(f"\nswe-qa: {len(items)} tasks")
    assigns = assign_splits(items, stratum_keys=("repo", "difficulty"))
    n_pub, n_held = write_manifest(
        assigns, public_path=SWE_QA_PUBLIC, heldout_path=SWE_QA_HELD,
    )
    print(f"  public:  {n_pub:3d} → {SWE_QA_PUBLIC.relative_to(_PROJECT_ROOT)}")
    print(f"  heldout: {n_held:3d} → {SWE_QA_HELD.relative_to(_PROJECT_ROOT)}")
    _print_strata("swe-qa", assigns)


def _print_strata(label: str, assigns) -> None:
    from collections import Counter
    by = Counter()
    for a in assigns:
        by[(a.stratum, a.split)] += 1
    print(f"  {label} stratum allocation:")
    strata = sorted({s for (s, _) in by})
    for s in strata:
        pub = by[(s, "public")]
        held = by[(s, "heldout")]
        print(f"    {','.join(s):20s}  public={pub:>3d}  heldout={held:>3d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--needle-max-per-repo", type=int, default=100,
                    help="needle dataset cap (default 100 — full v1.0).")
    args = ap.parse_args()
    print(f"Freezing splits at HELDOUT_FRACTION={HELDOUT_FRACTION:.2f}")
    _freeze_needle(args.needle_max_per_repo)
    _freeze_swe_qa()
    print("\nDone. Public manifests are tracked in git; held-out manifests are gitignored.")


if __name__ == "__main__":
    main()
