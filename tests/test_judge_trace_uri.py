"""Verify the runner wires Judge.trace_uri_for into Telemetry.trace_uri."""
from __future__ import annotations

from pathlib import Path

import pytest

from tokenbench.core.schemas import RepoRef, Task
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.judges.base import Judge
from tokenbench.judges.llm_judge import LLMJudge
from tokenbench.models.mock import MockModel
from tokenbench.providers.mock import MockRAGProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import Runner

from tests.test_llm_judge import _ScriptedModel, _vote


def _needle_task() -> Task:
    return Task(
        task_id="needle-trace-0001",
        dataset_version="1.0.0",
        task_type="needle_function",
        question="What is the answer? GOLD: yes",
        repo=RepoRef(url="x", commit="abc"),
        gold="yes",
        needle="yes",
        scoring="auto_contains",
        canary="TOKENBENCH-CANARY-test",
        license="MIT",
    )


def test_auto_contains_judge_writes_no_trace(tmp_path: Path):
    j = AutoContainsJudge()
    assert j.trace_uri_for(_needle_task()) is None
    store = ResultsStore(tmp_path / "rec.jsonl")
    runner = Runner(store)
    rec = runner.run_cell(
        _needle_task(), MockRAGProvider(), MockModel(),
        judge=j, repeat=0, seed=0,
    )
    assert rec.telemetry.trace_uri is None


def test_llm_judge_records_audit_path_in_trace_uri(tmp_path: Path):
    """A judge-scored task records the audit log path in Telemetry.trace_uri.

    Uses a scripted judge model to avoid gateway calls.
    """
    judge_model = _ScriptedModel("opus-test", [_vote(2, 2, 2)] * 3)
    judge = LLMJudge(judge_model, n_votes=3, audit_dir=tmp_path)
    assert judge.trace_uri_for(_needle_task()) == str(judge.audit_path)


def test_judge_base_default_returns_none():
    """Custom judges that don't override trace_uri_for get None."""
    class _StubJudge(Judge):
        name = "stub"

        def score(self, task, model_output):
            from tokenbench.core.schemas import Score
            return Score(correct=True, raw=1.0, scorer="auto_contains")

    j = _StubJudge()
    assert j.trace_uri_for(_needle_task()) is None
