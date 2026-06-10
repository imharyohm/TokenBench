"""Three mock providers with different (build, per-query) cost profiles.

Used to demonstrate the Pareto frontier and amortization curve in run_demo.py:
- MockRawProvider: zero build, large per-query (dump-it-all baseline)
- MockRAGProvider: small build, small per-query (typical RAG)
- MockGraphifyProvider: huge build, tiny per-query (amortizes well at high V)
"""

from __future__ import annotations

from ..core.schemas import Task
from ..core.tokenizer import count_tokens
from .base import BuildArtifact, Provider, RetrievedContext


def _wrap(question: str, gold: str, context: str) -> str:
    """Standardized prompt wrapper used by every provider so prompt format
    is not a confound across providers."""
    return (
        "You are answering a question about a codebase.\n"
        f"GOLD: {gold}\n"  # mock-only: lets MockModel decide correctness
        f"CONTEXT:\n{context}\n"
        f"QUESTION: {question}\n"
        "ANSWER:"
    )


class _MockProvider(Provider):
    def __init__(
        self,
        name: str,
        *,
        build_tokens: int,
        context_tokens: int,
        version: str = "0.0.1-mock",
    ):
        self.name = name
        self.version = version
        self.config = {"build_tokens": build_tokens, "context_tokens": context_tokens}
        self._build_tokens = build_tokens
        self._context_tokens = context_tokens

    def build(self, task: Task) -> BuildArtifact:
        return BuildArtifact(payload=None, build_tokens_norm=self._build_tokens)

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        # Synthesize a context blob that tokenizes to ~_context_tokens tokens.
        # "word " is 1 token under o200k_base, so this gives a tight count.
        context = ("word " * self._context_tokens).strip()
        prompt = _wrap(task.question, task.gold, context)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))


class MockRawProvider(_MockProvider):
    def __init__(self):
        super().__init__("mock-raw", build_tokens=0, context_tokens=4000)


class MockRAGProvider(_MockProvider):
    def __init__(self):
        super().__init__("mock-rag", build_tokens=2_000, context_tokens=400)


class MockGraphifyProvider(_MockProvider):
    def __init__(self):
        super().__init__("mock-graphify", build_tokens=200_000, context_tokens=80)
