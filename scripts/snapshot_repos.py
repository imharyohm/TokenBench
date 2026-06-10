"""Pull pinned repo snapshots at exact commit SHAs and content-address the result.

Usage:  python scripts/snapshot_repos.py
Reads the pinned repo list from `tokenbench/datasets/repo_pins.py` and writes
each snapshot under artifacts/repos/<short_id>/. Re-running is idempotent: if
the recorded sha256 matches what's on disk, the repo is left alone.

Hashing rule: see `tokenbench.datasets.repo_pins.hash_tree` — tool byproducts
(graphify-out/, __pycache__/, ...) are excluded so the hash is stable across
downstream operations.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenbench.datasets.repo_pins import REPO_PINS, hash_tree  # noqa: E402

ARTIFACTS = ROOT / "artifacts" / "repos"


def fetch(pin) -> tuple[Path, str]:
    dest = ARTIFACTS / pin.short_id
    if dest.exists():
        existing = hash_tree(dest)
        if existing == pin.snapshot_sha256:
            print(f"[ok]   {pin.short_id}  cached  sha256={existing[:12]}…")
            return dest, existing
        print(f"[warn] {pin.short_id}  hash mismatch; re-fetching")
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] {pin.short_id}  {pin.url} @ {pin.commit[:12]}")
    subprocess.run(
        ["git", "clone", "--quiet", pin.url, str(dest)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "checkout", "--quiet", pin.commit],
        check=True,
    )
    shutil.rmtree(dest / ".git", ignore_errors=True)
    sha = hash_tree(dest)
    print(f"        sha256={sha[:12]}…")
    return dest, sha


def main():
    print(f"snapshotting {len(REPO_PINS)} repos under {ARTIFACTS}\n")
    actuals = {}
    for pin in REPO_PINS:
        _, sha = fetch(pin)
        actuals[pin.short_id] = sha

    print("\n--- recorded sha256 (paste into repo_pins.py if first run) ---")
    for k, v in actuals.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
