"""Auto-scorer for RepoQA-style needle tasks. Zero judge risk: the gold
needle either appears in the model output or it doesn't."""

from __future__ import annotations

from ..core.schemas import Score, Task
from .base import Judge


class AutoContainsJudge(Judge):
    name = "auto_contains"

    def score(self, task: Task, model_output: str) -> Score:
        needle = task.needle or task.gold
        correct = needle.lower() in model_output.lower()
        return Score(correct=correct, raw=1.0 if correct else 0.0, scorer="auto_contains")
