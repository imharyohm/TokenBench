"""Zero-context provider — the priors-only floor (Chunk 6 deliverable A).

Sends the question to the model with an EMPTY <context>. The model must
answer from its training-time priors alone, no retrieval, no repo content.

Purpose: a method that cannot beat this is worse than no retrieval at all.
Pareto plots should always show every real provider strictly above this
floor; if not, the method is adding noise, not signal.

Frozen config: empty context, identical prompt scaffold as every other
provider (so prompt-format is not a confound — only the context payload
differs). build_tokens_norm = 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.schemas import Task
from ..core.tokenizer import count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import freeform_prompt, standard_prompt

FROZEN_CONFIG = {
    "context": "(empty)",
    "policy": "priors_only",
}


@dataclass(frozen=True)
class _ZeroPayload:
    pass


class ZeroContextProvider(Provider):
    """Empty context. The model must answer from priors."""

    name = "zero-context"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def build(self, task: Task) -> BuildArtifact:
        return BuildArtifact(payload=_ZeroPayload(), build_tokens_norm=0)

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        wrap = freeform_prompt if task.scoring == "llm_judge" else standard_prompt
        prompt = wrap(context="", question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
