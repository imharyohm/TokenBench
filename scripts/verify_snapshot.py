"""Verify that an on-disk pinned snapshot matches its recorded sha256.

Usage:
    python scripts/verify_snapshot.py                # verify all pins
    python scripts/verify_snapshot.py click          # by short_id
    python scripts/verify_snapshot.py needle-rich-0006   # by task_id

Exit codes:
    0  all checked snapshots verified
    1  at least one snapshot missing or hash mismatch
    2  argument error (unknown id)

This is the Chunk 4 deliverable #1 verifier. It is the gate the snapshot
must pass before any task referencing it can be scored.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenbench.datasets.repo_pins import REPO_PINS, hash_tree  # noqa: E402

ARTIFACTS = ROOT / "artifacts" / "repos"


def _resolve_pins(arg: str | None):
    if arg is None:
        return list(REPO_PINS)
    by_short = {p.short_id: p for p in REPO_PINS}
    if arg in by_short:
        return [by_short[arg]]
    # task_id form: "needle-<short_id>-NNNN"
    if arg.startswith("needle-"):
        parts = arg.split("-")
        if len(parts) >= 3 and parts[1] in by_short:
            return [by_short[parts[1]]]
    return []


def verify_one(pin) -> tuple[bool, str]:
    dest = ARTIFACTS / pin.short_id
    if not dest.exists():
        return False, f"missing snapshot directory: {dest}"
    if pin.snapshot_sha256 is None:
        return False, "no snapshot_sha256 recorded in repo_pins.py"
    actual = hash_tree(dest)
    if actual != pin.snapshot_sha256:
        return False, (
            f"hash mismatch\n"
            f"    recorded: {pin.snapshot_sha256}\n"
            f"    actual:   {actual}\n"
            f"    (re-run scripts/snapshot_repos.py if commit changed; "
            f"otherwise the tree was tampered with)"
        )
    return True, f"sha256={actual[:12]}…"


def main(argv: list[str]) -> int:
    arg = argv[1] if len(argv) > 1 else None
    pins = _resolve_pins(arg)
    if not pins:
        print(f"unknown id: {arg!r}", file=sys.stderr)
        print(f"known short_ids: {[p.short_id for p in REPO_PINS]}", file=sys.stderr)
        return 2

    failed = 0
    for pin in pins:
        ok, msg = verify_one(pin)
        tag = "[ok]  " if ok else "[FAIL]"
        print(f"{tag} {pin.short_id}  {msg}")
        if not ok:
            failed += 1

    if failed:
        print(f"\n{failed}/{len(pins)} snapshot(s) failed verification.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
