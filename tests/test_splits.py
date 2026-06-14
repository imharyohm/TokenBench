"""Tests for tokenbench.datasets.splits — Chunk 6 deliverable E."""

from __future__ import annotations

from pathlib import Path

import pytest

from tokenbench.datasets.splits import (
    HELDOUT_FRACTION,
    SplitAssignment,
    _heldout_count,
    assign_splits,
    load_manifest,
    write_manifest,
)


def test_heldout_count_rounds_at_5_tasks():
    # 5 * 0.20 = 1.0 → round to 1
    assert _heldout_count(5) == 1


def test_heldout_count_rounds_at_10_tasks():
    assert _heldout_count(10) == 2


def test_heldout_count_one_task_yields_zero():
    """A 1-task stratum can't have 0.2 of itself held out — rounds to 0."""
    assert _heldout_count(1) == 0


def test_heldout_count_zero_tasks_zero():
    assert _heldout_count(0) == 0


def test_assign_splits_holds_out_last_by_task_id():
    items = [{"task_id": f"t{i:02d}", "repo": "click"} for i in range(10)]
    assigns = assign_splits(items, stratum_keys=("repo",))
    by_split = {a.task_id: a.split for a in assigns}
    # 10 * 0.2 = 2 held out → last 2 by task_id within stratum
    assert by_split["t08"] == "heldout"
    assert by_split["t09"] == "heldout"
    assert by_split["t07"] == "public"
    assert by_split["t00"] == "public"


def test_assign_splits_input_order_independent():
    items_a = [{"task_id": f"t{i}", "repo": "click"} for i in range(10)]
    items_b = list(reversed(items_a))
    a = {x.task_id: x.split for x in assign_splits(items_a, stratum_keys=("repo",))}
    b = {x.task_id: x.split for x in assign_splits(items_b, stratum_keys=("repo",))}
    assert a == b


def test_assign_splits_stratifies_per_key():
    items = [{"task_id": f"click-{i}", "repo": "click"} for i in range(10)] + \
            [{"task_id": f"rich-{i}", "repo": "rich"} for i in range(10)]
    assigns = assign_splits(items, stratum_keys=("repo",))
    held = [a for a in assigns if a.split == "heldout"]
    # Both repos have 10 tasks each → 2 each held out
    assert sum(1 for a in held if a.task_id.startswith("click-")) == 2
    assert sum(1 for a in held if a.task_id.startswith("rich-")) == 2


def test_assign_splits_total_proportion():
    items = [{"task_id": f"t{i:03d}", "repo": "x"} for i in range(100)]
    assigns = assign_splits(items, stratum_keys=("repo",))
    n_held = sum(1 for a in assigns if a.split == "heldout")
    assert n_held == 20


def test_assign_splits_multi_key_stratification():
    """repo × difficulty stratification, used for SWE-QA."""
    items = []
    for repo in ("click", "rich"):
        for diff in ("easy", "medium"):
            for i in range(5):
                items.append({"task_id": f"{repo}-{diff}-{i}",
                              "repo": repo, "difficulty": diff})
    assigns = assign_splits(items, stratum_keys=("repo", "difficulty"))
    by_stratum_split: dict = {}
    for a in assigns:
        by_stratum_split.setdefault((a.stratum, a.split), 0)
        by_stratum_split[(a.stratum, a.split)] += 1
    # Each stratum has 5 tasks → 1 held out
    for stratum in [("click", "easy"), ("click", "medium"),
                    ("rich", "easy"), ("rich", "medium")]:
        assert by_stratum_split[(stratum, "public")] == 4
        assert by_stratum_split[(stratum, "heldout")] == 1


def test_assign_splits_carries_stratum_in_assignment():
    items = [{"task_id": f"t{i}", "repo": "click", "difficulty": "easy"}
             for i in range(5)]
    assigns = assign_splits(items, stratum_keys=("repo", "difficulty"))
    assert assigns[0].stratum == ("click", "easy")


def test_assign_splits_empty_input():
    assigns = assign_splits([], stratum_keys=("repo",))
    assert assigns == []


def test_assign_splits_is_deterministic():
    """No hidden seed — same input must produce same output across runs."""
    items = [{"task_id": f"t{i:03d}", "repo": ("a", "b")[i % 2]} for i in range(50)]
    a = assign_splits(items, stratum_keys=("repo",))
    b = assign_splits(items, stratum_keys=("repo",))
    assert [(x.task_id, x.split) for x in a] == [(x.task_id, x.split) for x in b]


# ---------- write_manifest / load_manifest roundtrip ----------


def test_manifest_roundtrip(tmp_path: Path):
    items = [{"task_id": f"t{i:02d}", "repo": "click"} for i in range(10)]
    assigns = assign_splits(items, stratum_keys=("repo",))
    pub = tmp_path / "public.tsv"
    held = tmp_path / "heldout.tsv"
    n_pub, n_held = write_manifest(assigns, public_path=pub, heldout_path=held)
    assert n_pub == 8 and n_held == 2
    pub_set = load_manifest(pub)
    held_set = load_manifest(held)
    # No overlap, complete coverage
    assert pub_set & held_set == set()
    assert pub_set | held_set == {a.task_id for a in assigns}


def test_load_manifest_missing_returns_empty(tmp_path: Path):
    assert load_manifest(tmp_path / "nonexistent.tsv") == set()


def test_load_manifest_skips_comments(tmp_path: Path):
    p = tmp_path / "m.tsv"
    p.write_text("# comment 1\nt001\trepo\n# another comment\nt002\trepo\n")
    assert load_manifest(p) == {"t001", "t002"}


def test_heldout_fraction_locked_at_20_pct():
    assert HELDOUT_FRACTION == 0.20
