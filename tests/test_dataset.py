from pathlib import Path

import pytest

from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.datasets.repo_pins import REPO_PINS

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts" / "repos"


def _snapshots_present() -> bool:
    return all((ARTIFACTS / pin.short_id).exists() for pin in REPO_PINS)


pytestmark = pytest.mark.skipif(
    not _snapshots_present(),
    reason="repo snapshots not on disk; run scripts/snapshot_repos.py",
)


def test_emits_tasks_with_expected_shape():
    ds = NeedleCodebaseDataset(max_tasks_per_repo=2)
    tasks = list(ds)
    assert len(tasks) > 0
    for t in tasks:
        assert t.task_type == "needle_function"
        assert t.scoring == "auto_contains"
        assert t.dataset_version == ds.dataset_version
        assert t.canary.startswith("TOKENBENCH-CANARY-")
        assert t.gold == t.needle  # auto_contains scorer uses needle
        assert t.repo.commit  # pinned commit recorded
        assert t.meta.get("repo_id") in {p.short_id for p in REPO_PINS}


def test_max_tasks_per_repo_is_respected():
    ds = NeedleCodebaseDataset(max_tasks_per_repo=2)
    tasks = list(ds)
    by_repo = {}
    for t in tasks:
        by_repo.setdefault(t.meta["repo_id"], 0)
        by_repo[t.meta["repo_id"]] += 1
    for n in by_repo.values():
        assert n <= 2


def test_task_ids_are_unique():
    ds = NeedleCodebaseDataset(max_tasks_per_repo=4)
    ids = [t.task_id for t in ds]
    assert len(ids) == len(set(ids))
