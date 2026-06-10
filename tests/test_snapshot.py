"""Tests for snapshot hashing and the verifier (Chunk 4 deliverable #1)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tokenbench.datasets.repo_pins import (
    REPO_PINS,
    SNAPSHOT_EXCLUDE_DIRS,
    hash_tree,
)

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts" / "repos"
VERIFIER = ROOT / "scripts" / "verify_snapshot.py"


def _snapshots_present() -> bool:
    return all((ARTIFACTS / pin.short_id).exists() for pin in REPO_PINS)


pytestmark = pytest.mark.skipif(
    not _snapshots_present(),
    reason="repo snapshots not on disk; run scripts/snapshot_repos.py",
)


def test_recorded_hashes_match_disk():
    """The pins in REPO_PINS must match what hash_tree produces today."""
    for pin in REPO_PINS:
        assert pin.snapshot_sha256 is not None, f"{pin.short_id} missing recorded sha256"
        actual = hash_tree(ARTIFACTS / pin.short_id)
        assert actual == pin.snapshot_sha256, (
            f"{pin.short_id} hash drift: recorded={pin.snapshot_sha256[:12]} "
            f"actual={actual[:12]}"
        )


def test_byproducts_excluded_from_hash(tmp_path):
    """Adding files inside an excluded byproduct dir must NOT change the hash."""
    pin = REPO_PINS[0]  # click — smallest
    src = ARTIFACTS / pin.short_id
    dst = tmp_path / pin.short_id
    shutil.copytree(src, dst)
    baseline = hash_tree(dst)

    byproduct = dst / "graphify-out"
    byproduct.mkdir(exist_ok=True)
    (byproduct / "novel-file.json").write_text('{"injected": true}')
    nested = byproduct / "cache" / "ast"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "deadbeef.json").write_text('{"x": 1}')

    pycache = dst / "src" / "__pycache__"
    pycache.mkdir(parents=True, exist_ok=True)
    (pycache / "stale.pyc").write_bytes(b"\x00\x01\x02")

    assert hash_tree(dst) == baseline


def test_tampered_content_changes_hash(tmp_path):
    """Modifying any tracked file must change the hash."""
    pin = REPO_PINS[0]
    src = ARTIFACTS / pin.short_id
    dst = tmp_path / pin.short_id
    shutil.copytree(src, dst)

    target = dst / "README.md"
    target.write_bytes(target.read_bytes() + b"X")

    assert hash_tree(dst) != pin.snapshot_sha256


def test_verifier_rejects_tampered_snapshot(tmp_path, monkeypatch):
    """The verifier must exit non-zero and print FAIL on a tampered tree."""
    import importlib.util

    pin = REPO_PINS[0]
    src = ARTIFACTS / pin.short_id

    # Build a fake artifacts/repos/<short_id>/ with a tampered copy.
    fake_artifacts = tmp_path / "repos"
    fake_artifacts.mkdir()
    dst = fake_artifacts / pin.short_id
    shutil.copytree(src, dst)
    target = dst / "README.md"
    target.write_bytes(target.read_bytes() + b"TAMPERED")

    # Load verify_snapshot.py as a module, then redirect its ARTIFACTS at the
    # tampered tree. This exercises the same code path as the CLI without
    # depending on filesystem symlinks behaving consistently.
    spec = importlib.util.spec_from_file_location("verify_snapshot", VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ARTIFACTS", fake_artifacts)

    rc = mod.main(["verify_snapshot.py", pin.short_id])
    assert rc == 1, f"expected exit 1, got {rc}"

    ok, msg = mod.verify_one(pin)
    assert not ok
    assert "hash mismatch" in msg


def test_excluded_dirs_include_known_byproducts():
    """Sanity: the exclusion set covers tools the project actually uses."""
    expected = {"graphify-out", "__pycache__", ".pytest_cache", ".git"}
    assert expected <= SNAPSHOT_EXCLUDE_DIRS
