"""Scoring interface. Runs OUTSIDE the provider's environment per
DECISIONS.md #3 (isolation boundary)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..core.schemas import Score, Task


class Judge(ABC):
    name: str

    @abstractmethod
    def score(self, task: Task, model_output: str) -> Score: ...

    def trace_uri_for(self, task: Task) -> Optional[str]:
        """Return a URI/path for the audit trail of judge calls on this task.

        Default: None (e.g. AutoContainsJudge has no audit log to point at).
        Judges that record per-call prompts/responses (e.g. LLMJudge) override
        this to return a stable pointer that gets stored in
        Telemetry.trace_uri on the RunRecord.
        """
        return None
