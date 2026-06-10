"""Provider plugin interface — the SINGLE controlled variable in a run.

Per §1[3]: each context method (raw, RAG, Graphify, repo-map, LLMLingua-2)
implements this interface. Everything else is frozen between runs; only the
provider changes. That's what gives the benchmark validity.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.schemas import Task


@dataclass(frozen=True)
class BuildArtifact:
    """Result of a one-time build step (RAG index, knowledge graph, etc.).

    build_tokens_norm tracks the one-time cost; it is amortized over V queries
    via metrics.tpca(V).
    """

    payload: object  # opaque to the runner; provider-specific
    build_tokens_norm: int


@dataclass(frozen=True)
class RetrievedContext:
    """The context the provider returns for a single query."""

    text: str
    input_tokens_norm: int  # token cost of `text` under o200k_base


class Provider(ABC):
    """Returns a context string for a question against a repo.

    Lifecycle:
      1. build(task) -> artifact (one-time, amortized)
      2. retrieve(task, artifact) -> context for this query
    """

    name: str
    version: str
    config: dict

    @abstractmethod
    def build(self, task: Task) -> BuildArtifact: ...

    @abstractmethod
    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext: ...
