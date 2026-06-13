"""Tests for tokenbench.judges.llm_judge.LLMJudge (Chunk 5 deliverable 2).

Uses a scriptable in-process Model, never the real gateway.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

from tokenbench.core.schemas import RepoRef, Task
from tokenbench.judges.llm_judge import (
    DEFAULT_JUDGE_MODEL,
    JUDGE_RUBRIC_VERSION,
    LLMJudge,
)
from tokenbench.models.base import Model, ModelResponse


class _ScriptedModel(Model):
    """Returns whatever string is next in `responses` on each .complete() call."""

    def __init__(self, name: str, responses: list[str]):
        self.name = name
        self.provider = "scripted"
        self._iter: Iterator[str] = iter(responses)
        self.calls: list[dict] = []

    def complete(self, prompt: str, *, max_tokens: int = 1024, seed: int = 0) -> ModelResponse:
        text = next(self._iter)
        self.calls.append({"prompt": prompt, "seed": seed, "max_tokens": max_tokens})
        return ModelResponse(
            text=text,
            native_input_tokens=len(prompt) // 4,
            native_output_tokens=len(text) // 4,
            norm_input_tokens=len(prompt) // 4,
            norm_output_tokens=len(text) // 4,
            latency_ms=1,
            raw_trace={"text": text},
        )


def _task(scoring: str = "llm_judge") -> Task:
    return Task(
        task_id="swe-test-0001",
        dataset_version="1.0.0",
        task_type="repo_qa",
        question="How does X work?",
        repo=RepoRef(url="x", commit="abc"),
        gold="Reference: X works by doing Y.",
        scoring=scoring,
        canary="TOKENBENCH-CANARY-test",
        license="MIT",
    )


def _vote(c: int, comp: int, f: int, rationale: str = "ok") -> str:
    return json.dumps({
        "correctness": c,
        "completeness": comp,
        "faithfulness": f,
        "rationale": rationale,
    })


def test_unanimous_pass_returns_correct_true_with_confidence_1(tmp_path: Path):
    model = _ScriptedModel("opus-test", [_vote(2, 2, 2)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "candidate answer")
    assert score.correct is True
    assert score.raw == pytest.approx(1.0)
    assert score.scorer == "llm_judge"


def test_unanimous_fail(tmp_path: Path):
    model = _ScriptedModel("opus-test", [_vote(0, 0, 0)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "wrong")
    assert score.correct is False
    assert score.raw == pytest.approx(0.0)


def test_majority_2_of_3_pass(tmp_path: Path):
    model = _ScriptedModel("opus-test", [
        _vote(2, 2, 2),  # pass
        _vote(0, 0, 0),  # fail
        _vote(2, 2, 2),  # pass
    ])
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "candidate")
    assert score.correct is True
    assert score.raw == pytest.approx(2.0 / 3.0)


def test_pass_floor_faithfulness_at_one_passes_under_v1_1_0(tmp_path: Path):
    """Under JUDGE_RUBRIC_VERSION=1.1.0 the faithfulness floor is >=1 (not ==2).

    DECISIONS.md #13: per-dim diagnostics on the 210-task gold set showed
    faithfulness failed to discriminate human-pass from human-fail (gap 0.07
    vs 0.97-1.13 on the other dims). The strict ==2 floor was the dominant
    source of false negatives. v1.1.0 relaxes faithfulness to >=1; this test
    pins that behavior so a future rubric bump shows up here.
    """
    model = _ScriptedModel("opus-test", [_vote(2, 2, 1)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "candidate")
    assert score.correct is True
    # faithfulness=0 still trips the floor
    model0 = _ScriptedModel("opus-test", [_vote(2, 2, 0)] * 3)
    judge0 = LLMJudge(model0, n_votes=3, audit_dir=tmp_path)
    assert judge0.score(_task(), "candidate").correct is False


def test_correctness_floor(tmp_path: Path):
    """correctness=0 fails even if completeness/faithfulness are perfect."""
    model = _ScriptedModel("opus-test", [_vote(0, 2, 2)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "candidate")
    assert score.correct is False


def test_judge_refuses_answering_models():
    with pytest.raises(ValueError, match="answering model"):
        LLMJudge(_ScriptedModel("bedrock.anthropic.claude-sonnet-4-5", []))
    with pytest.raises(ValueError, match="answering model"):
        LLMJudge(_ScriptedModel("openai.gpt-4o-mini", []))


def test_judge_rejects_even_n_votes(tmp_path: Path):
    with pytest.raises(ValueError, match="odd"):
        LLMJudge(_ScriptedModel("opus-test", []), n_votes=2)
    with pytest.raises(ValueError, match="odd"):
        LLMJudge(_ScriptedModel("opus-test", []), n_votes=4)


def test_judge_rejects_n_votes_below_3(tmp_path: Path):
    with pytest.raises(ValueError, match=">= 3"):
        LLMJudge(_ScriptedModel("opus-test", []), n_votes=1)


def test_judge_refuses_non_judge_scoring_task(tmp_path: Path):
    model = _ScriptedModel("opus-test", [])
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    bad_task = _task(scoring="auto_contains")
    with pytest.raises(ValueError, match="expected 'llm_judge'"):
        judge.score(bad_task, "x")


def test_audit_log_written_with_full_prompt_and_response(tmp_path: Path):
    raw = _vote(2, 2, 2, "looks good")
    model = _ScriptedModel("opus-test", [raw] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    judge.score(_task(), "candidate")
    audit_lines = judge.audit_path.read_text().splitlines()
    assert len(audit_lines) == 1
    rec = json.loads(audit_lines[0])
    assert rec["task_id"] == "swe-test-0001"
    assert rec["judge_model"] == "opus-test"
    assert rec["rubric_version"] == JUDGE_RUBRIC_VERSION
    assert rec["majority_pass"] is True
    assert rec["confidence"] == pytest.approx(1.0)
    assert len(rec["votes"]) == 3
    for v in rec["votes"]:
        assert "prompt" in v and "raw_response" in v
        assert v["dims"]["correctness"] == 2
        assert v["passed"] is True


def test_anonymized_prompt_does_not_leak_provider_or_model(tmp_path: Path):
    """Judge prompt must not contain provider name or model id of answer-side."""
    model = _ScriptedModel("opus-test", [_vote(2, 2, 2)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    judge.score(_task(), "candidate from rag-bm25 + sonnet-4-5")
    # Prompt is reconstructed identically on each vote — inspect the model's
    # call log. The candidate text WILL contain those words because the user
    # put them there; the test is that the JUDGE PROMPT TEMPLATE itself does
    # not introduce provider/model identifiers in any control region.
    for call in model.calls:
        prompt = call["prompt"]
        # The candidate region is between the CANDIDATE markers; exclude it.
        before, _, rest = prompt.partition("<<<CANDIDATE>>>")
        candidate_block, _, after = rest.partition("<<<END CANDIDATE>>>")
        control = before + after
        for forbidden in ("rag-bm25", "sonnet-4-5", "gpt-4o-mini",
                          "graphify", "llmlingua", "raw-dump", "repo-map"):
            assert forbidden not in control, (
                f"control region of judge prompt leaks {forbidden!r}"
            )


def test_parse_failure_treated_as_fail_and_logged(tmp_path: Path):
    model = _ScriptedModel("opus-test", [
        "this is not JSON at all",
        _vote(2, 2, 2),
        _vote(2, 2, 2),
    ])
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    score = judge.score(_task(), "candidate")
    # 1 fail (parse error) + 2 pass = majority pass, confidence 2/3
    assert score.correct is True
    assert score.raw == pytest.approx(2.0 / 3.0)
    rec = json.loads(judge.audit_path.read_text().splitlines()[0])
    assert rec["votes"][0]["dims"].get("_parse_error") is True


def test_default_judge_model_is_locked_value():
    assert DEFAULT_JUDGE_MODEL == "bedrock.anthropic.claude-opus-4-7"


def test_per_call_shuffle_salt_makes_prompts_distinct(tmp_path: Path):
    model = _ScriptedModel("opus-test", [_vote(2, 2, 2)] * 3)
    judge = LLMJudge(model, n_votes=3, audit_dir=tmp_path)
    judge.score(_task(), "candidate")
    prompts = [c["prompt"] for c in model.calls]
    assert len(set(prompts)) == 3, "vote-salt failed to differentiate prompts"
