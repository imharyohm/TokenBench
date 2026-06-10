"""Tests for the SWE-QA loader (Chunk 5 deliverable 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenbench.datasets.repo_pins import REPO_PINS
from tokenbench.datasets.swe_qa import QUESTIONS_DIR, SweQaDataset

QUESTIONS_FILE = QUESTIONS_DIR / "v1.0.0" / "questions.jsonl"

pytestmark = pytest.mark.skipif(
    not QUESTIONS_FILE.exists(),
    reason="SWE-QA questions file not yet authored",
)


def test_emits_tasks_with_expected_shape():
    ds = SweQaDataset()
    tasks = list(ds)
    assert len(tasks) > 0
    repo_ids = {p.short_id for p in REPO_PINS}
    for t in tasks:
        assert t.task_type == "repo_qa"
        assert t.scoring == "llm_judge"
        assert t.dataset_version == ds.dataset_version
        assert t.canary == f"TOKENBENCH-CANARY-swe-qa-{ds.dataset_version}"
        assert t.gold  # reference text non-empty
        assert t.needle is None
        assert t.repo.commit  # pinned commit propagated
        assert t.meta["repo_id"] in repo_ids


def test_task_ids_are_unique():
    tasks = list(SweQaDataset())
    ids = [t.task_id for t in tasks]
    assert len(ids) == len(set(ids))


def test_starter_set_covers_all_three_repos():
    """Starter set must touch click/rich/httpx so judge calibration is balanced."""
    tasks = list(SweQaDataset())
    by_repo: dict[str, int] = {}
    for t in tasks:
        by_repo[t.meta["repo_id"]] = by_repo.get(t.meta["repo_id"], 0) + 1
    assert set(by_repo) == {"click", "rich", "httpx"}, by_repo


def test_rejects_unknown_repo_id(tmp_path: Path):
    bad = tmp_path / "questions.jsonl"
    bad.write_text(json.dumps({
        "task_id": "swe-bogus-0000",
        "repo_id": "not-a-real-repo",
        "question": "?",
        "reference": "x",
    }) + "\n")
    ds = SweQaDataset(questions_path=bad)
    with pytest.raises(ValueError, match="unknown repo_id"):
        list(ds)


def test_rejects_missing_required_field(tmp_path: Path):
    bad = tmp_path / "questions.jsonl"
    bad.write_text(json.dumps({
        "task_id": "swe-click-0999",
        "repo_id": "click",
        # question missing
        "reference": "x",
    }) + "\n")
    ds = SweQaDataset(questions_path=bad)
    with pytest.raises(ValueError, match="missing required field"):
        list(ds)


def test_missing_questions_file_raises(tmp_path: Path):
    ds = SweQaDataset(questions_path=tmp_path / "nope.jsonl")
    with pytest.raises(FileNotFoundError):
        list(ds)
