"""Raw-dump provider — naive baseline (the floor).

Concatenates every Python file in the pinned repo into one big context, then
truncates at a frozen token budget. No preprocessing → build_tokens_norm = 0.

Per DECISIONS.md #6 the budget is frozen. We pick 80,000 norm tokens because
that fits comfortably in modern model windows but is large enough to expose
the cost of dumping everything (vs RAG's ~1k/cell).

Anything that can't beat this floor on the accuracy-vs-tokens Pareto is
worse than doing nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.schemas import Task
from ..core.tokenizer import _encoder, count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import standard_prompt

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "artifacts" / "repos"

FROZEN_CONFIG = {
    "context_token_budget": 80_000,
    "file_glob": "*.py",
    "truncate_strategy": "head",
}


@dataclass(frozen=True)
class _RawPayload:
    repo_id: str
    text: str  # already truncated to budget


def _load_repo_text(repo_id: str) -> str:
    repo_root = ARTIFACTS / repo_id
    if not repo_root.exists():
        raise FileNotFoundError(
            f"Repo snapshot missing: {repo_root}. Run scripts/snapshot_repos.py."
        )
    parts: list[str] = []
    for f in sorted(repo_root.rglob(FROZEN_CONFIG["file_glob"])):
        rel = f.relative_to(repo_root).as_posix()
        if any(p.startswith(".") for p in rel.split("/")):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        parts.append(f"# file: {rel}\n{text}")
    return "\n\n".join(parts)


def _truncate_to_budget(text: str, budget: int) -> str:
    enc = _encoder()
    ids = enc.encode(text)
    if len(ids) <= budget:
        return text
    return enc.decode(ids[:budget])


class RawDumpProvider(Provider):
    """Frozen-config naive dump. Concatenate, truncate, send."""

    name = "raw-dump"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def __init__(self):
        self._cache: dict[str, str] = {}

    def _text(self, repo_id: str) -> str:
        if repo_id not in self._cache:
            full = _load_repo_text(repo_id)
            self._cache[repo_id] = _truncate_to_budget(
                full, FROZEN_CONFIG["context_token_budget"]
            )
        return self._cache[repo_id]

    def build(self, task: Task) -> BuildArtifact:
        repo_id = task.meta.get("repo_id")
        if not repo_id:
            raise ValueError(f"task {task.task_id} missing meta.repo_id")
        text = self._text(repo_id)
        return BuildArtifact(payload=_RawPayload(repo_id=repo_id, text=text), build_tokens_norm=0)

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        payload: _RawPayload = artifact.payload  # type: ignore[assignment]
        prompt = standard_prompt(context=payload.text, question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
