"""LLM judge for free-form (SWE-QA) outputs.

Design (per chunks/CHUNK_05_judge.md and DECISIONS.md #9):

1. Separated judge model — DECISIONS.md #9 locks `bedrock.anthropic.claude-opus-4-7`.
   Must differ from any answering model in the same sweep (sonnet-4-5 / gpt-4o-mini)
   to avoid exact-model self-preference.

2. Multi-dimension rubric — correctness, completeness, faithfulness (no hallucination).
   Each dim graded {0, 1, 2}. The pass rule (rubric v1.1.0): every dim must reach
   its floor — correctness >= 1, completeness >= 1, faithfulness >= 1. v1.0.0 had
   faithfulness == 2; relaxed in v1.1.0 after per-dim calibration diagnostics
   showed faithfulness failed to discriminate (DECISIONS.md #13). The rubric
   prompt is versioned and frozen; only the binary aggregation rule changed.

3. N-way majority vote — N >= 3 (default 3). Each judge call is a fresh prompt
   with a different shuffle key. Final verdict is majority pass/fail; raw =
   (#pass votes) / N.

4. Anonymized inputs — the judge prompt never contains provider name, model name,
   sweep id, or any other side-channel. Only (question, reference_answer,
   model_output). Output is also lightly normalized (whitespace) so length cues
   don't telegraph provider behavior.

5. Audit trail — every judge call (full prompt + raw response + parsed dims)
   is appended to results/judge/<judge_run_id>.jsonl. Score.raw carries the
   vote share so calibration's ECE bin is meaningful.

The judge runs OUTSIDE the agent / provider environment per DECISIONS.md #3
(isolation boundary): the reference answer is loaded by the judge alone and
never enters provider context.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..core.schemas import Score, Task
from ..models.base import Model
from .base import Judge

JUDGE_RUBRIC_VERSION = "1.1.0"
DEFAULT_JUDGE_MODEL = "bedrock.anthropic.claude-opus-4-7"
DEFAULT_N_VOTES = 3

# Pass floor per dim. Tightening or loosening this is a JUDGE_RUBRIC_VERSION bump.
# v1.1.0 (2026-06-13): faithfulness 2→1. Per-dim diagnostics on 210-task gold
# set showed faithfulness mean=1.73 (human pass) vs 1.66 (human fail) — the dim
# did not discriminate, but the ==2 floor was driving 30% false-negative rate
# (37/122 human-pass tasks marked fail by the judge). Relaxing to ≥1 raised
# κ 0.609→0.806 and dropped ECE 0.20→0.09. Detail in DECISIONS.md change log.
PASS_FLOOR = {"correctness": 1, "completeness": 1, "faithfulness": 1}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_AUDIT_DIR = _PROJECT_ROOT / "results" / "judge"


JUDGE_PROMPT = """\
You are an expert code reviewer grading an answer to a question about an \
open-source Python library. Your job is to score the candidate answer along \
three dimensions, then return a strict JSON object.

You are NOT told who wrote the candidate answer. Do not speculate.

Question:
<<<QUESTION>>>
{question}
<<<END QUESTION>>>

Reference answer (ground truth — for grading only):
<<<REFERENCE>>>
{reference}
<<<END REFERENCE>>>

Candidate answer (to grade):
<<<CANDIDATE>>>
{candidate}
<<<END CANDIDATE>>>

Score each dimension on a 0/1/2 scale:

correctness  — Does the candidate get the technical facts right?
  0 = wrong or contradicts the reference on a key point.
  1 = mostly right; minor inaccuracy that doesn't change the conclusion.
  2 = correct on all key points.

completeness — Does the candidate cover the parts of the question the reference covers?
  0 = misses the main thing the question asks.
  1 = covers the core but misses a notable sub-point present in the reference.
  2 = covers what the reference covers (it may be more concise).

faithfulness — Is the candidate free of fabricated APIs, files, classes, or behavior?
  0 = invents a function/class/file that does not exist or claims behavior the library does not have.
  1 = no clear fabrication, but uses vague language that could mislead.
  2 = grounded in the actual library; no fabrication.

Return ONLY this JSON, nothing else:
{{
  "correctness": 0|1|2,
  "completeness": 0|1|2,
  "faithfulness": 0|1|2,
  "rationale": "<one or two sentences>"
}}
"""


@dataclass(frozen=True)
class JudgeVote:
    """One judge call's parsed verdict."""

    dims: dict
    rationale: str
    passed: bool
    raw_response: str
    prompt: str


def _passes_floor(dims: dict) -> bool:
    return all(dims.get(k, 0) >= floor for k, floor in PASS_FLOOR.items())


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_json(text: str) -> dict:
    """Extract the JSON object the judge was told to return.

    The judge sometimes wraps the JSON in prose despite the instruction; pull
    the first {...} balanced block. Raises ValueError on unparseable output.
    """
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError(f"judge returned no JSON object: {text[:200]!r}")
    blob = match.group(0)
    try:
        rec = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ValueError(f"judge returned invalid JSON: {e}: {blob[:200]!r}") from e
    for k in ("correctness", "completeness", "faithfulness"):
        if k not in rec:
            raise ValueError(f"judge JSON missing dim {k!r}: {rec}")
        v = rec[k]
        if not isinstance(v, int) or v not in (0, 1, 2):
            raise ValueError(f"judge JSON dim {k!r} not in {{0,1,2}}: {v!r}")
    rec.setdefault("rationale", "")
    return rec


def _normalize_candidate(text: str) -> str:
    """Light normalization to avoid length/format cues. NOT content rewriting."""
    return text.strip()


def _shuffle_key(task_id: str, vote_idx: int, salt: str) -> str:
    """Deterministic but unobservable salt per (task, vote) — the prompt is
    otherwise identical across votes, which would make the API cache returns
    look identical too. Adding the key forces the judge to re-evaluate.
    """
    h = hashlib.sha256(f"{salt}|{task_id}|{vote_idx}".encode()).hexdigest()
    return h[:16]


class LLMJudge(Judge):
    """Separated-model multi-dim majority-vote judge.

    Per call to .score(): runs `n_votes` judge inferences in series,
    each with the multi-dim rubric, parses the JSON, and majority-votes the
    pass/fail. Audit log written to `audit_path`.
    """

    name = "llm_judge"

    def __init__(
        self,
        judge_model: Model,
        *,
        n_votes: int = DEFAULT_N_VOTES,
        audit_dir: Path = DEFAULT_AUDIT_DIR,
        judge_run_id: Optional[str] = None,
        max_tokens: int = 256,
    ):
        if n_votes < 3 or n_votes % 2 == 0:
            raise ValueError(
                f"n_votes must be odd and >= 3 (got {n_votes}); "
                "majority vote needs an odd count"
            )
        if judge_model.name in {"bedrock.anthropic.claude-sonnet-4-5",
                                "openai.gpt-4o-mini"}:
            # Hard fail — these are answering models; using them as judge is
            # exact-model self-preference, banned by DECISIONS.md #9.
            raise ValueError(
                f"judge_model={judge_model.name!r} is an answering model in "
                "this benchmark; use a different model id (DECISIONS.md #9)."
            )
        self.judge_model = judge_model
        self.n_votes = n_votes
        self.judge_run_id = judge_run_id or f"judge-{uuid4().hex[:8]}"
        self.max_tokens = max_tokens
        audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = audit_dir / f"{self.judge_run_id}.jsonl"
        self._lock = threading.Lock()

    def trace_uri_for(self, task: Task) -> str:
        return str(self.audit_path)

    def score(self, task: Task, model_output: str) -> Score:
        if task.scoring != "llm_judge":
            raise ValueError(
                f"LLMJudge invoked on task with scoring={task.scoring!r}; "
                "expected 'llm_judge'"
            )
        candidate = _normalize_candidate(model_output)
        votes: list[JudgeVote] = []
        for vote_idx in range(self.n_votes):
            vote = self._vote(task, candidate, vote_idx)
            votes.append(vote)
        pass_count = sum(1 for v in votes if v.passed)
        majority_pass = pass_count > self.n_votes // 2
        confidence = pass_count / self.n_votes
        # raw = directional confidence: 1.0 = unanimous pass, 0.0 = unanimous fail.
        # (Calibration's ECE binning treats this as P(pass).)
        self._append_audit(task, candidate, votes, majority_pass, confidence)
        return Score(
            correct=majority_pass,
            raw=confidence,
            scorer="llm_judge",
        )

    def _vote(self, task: Task, candidate: str, vote_idx: int) -> JudgeVote:
        prompt = JUDGE_PROMPT.format(
            question=task.question,
            reference=task.gold,
            candidate=candidate,
        )
        # Append shuffle salt so the gateway can't return a cached identical
        # response across votes; visible to the model but content-free.
        prompt += f"\n\n[vote-salt: {_shuffle_key(task.task_id, vote_idx, self.judge_run_id)}]"
        resp = self.judge_model.complete(
            prompt, max_tokens=self.max_tokens, seed=vote_idx
        )
        try:
            dims = _parse_judge_json(resp.text)
        except ValueError:
            # On parse failure: count as fail (conservative) but keep raw output
            # in the audit log so calibration can see it.
            return JudgeVote(
                dims={"correctness": 0, "completeness": 0, "faithfulness": 0,
                      "_parse_error": True},
                rationale=f"PARSE_ERROR: {resp.text[:200]}",
                passed=False,
                raw_response=resp.text,
                prompt=prompt,
            )
        return JudgeVote(
            dims={k: dims[k] for k in ("correctness", "completeness", "faithfulness")},
            rationale=dims.get("rationale", ""),
            passed=_passes_floor(dims),
            raw_response=resp.text,
            prompt=prompt,
        )

    def _append_audit(
        self,
        task: Task,
        candidate: str,
        votes: list[JudgeVote],
        majority_pass: bool,
        confidence: float,
    ) -> None:
        record = {
            "judge_run_id": self.judge_run_id,
            "rubric_version": JUDGE_RUBRIC_VERSION,
            "judge_model": self.judge_model.name,
            "task_id": task.task_id,
            "dataset_version": task.dataset_version,
            "candidate": candidate,
            "n_votes": self.n_votes,
            "majority_pass": majority_pass,
            "confidence": confidence,
            "votes": [
                {
                    "dims": v.dims,
                    "rationale": v.rationale,
                    "passed": v.passed,
                    "raw_response": v.raw_response,
                    "prompt": v.prompt,
                }
                for v in votes
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self.audit_path.open("a") as fh:
                fh.write(line + "\n")
