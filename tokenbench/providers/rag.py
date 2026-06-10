"""BM25 RAG provider — first real Provider implementation.

Frozen config (per DECISIONS.md #6):
- chunker: per-file, fixed token-window with overlap
- retriever: BM25Okapi over whitespace tokens
- top-K: 5

Build cost = total tokens of indexed corpus (the cost a vector DB or
search engine charges to ingest). Per-query cost = the retrieved context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rank_bm25 import BM25Okapi

from ..core.schemas import Task
from ..core.tokenizer import count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import standard_prompt

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "artifacts" / "repos"

# Frozen config knobs — record as the provider config in run records.
FROZEN_CONFIG = {
    "chunk_tokens": 200,
    "chunk_overlap_tokens": 40,
    "top_k": 5,
    "tokenizer": "whitespace",
    "retriever": "bm25_okapi",
}

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[A-Za-z0-9]+")


@dataclass(frozen=True)
class _Chunk:
    repo_id: str
    file: str
    text: str
    norm_tokens: int


def _tokenize(text: str) -> list[str]:
    """Whitespace-ish tokenizer that also splits camelCase / snake_case
    weakly via the regex above. Good enough for BM25 over code."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _chunk_file(text: str, *, chunk_tokens: int, overlap: int) -> Iterable[str]:
    """Naive token-window chunker over o200k_base tokens, decoded back to
    text. Faithful to the reference tokenizer the metric uses."""
    from ..core.tokenizer import _encoder

    enc = _encoder()
    ids = enc.encode(text)
    if not ids:
        return []
    step = max(1, chunk_tokens - overlap)
    out = []
    for start in range(0, len(ids), step):
        piece = ids[start : start + chunk_tokens]
        if not piece:
            break
        out.append(enc.decode(piece))
        if start + chunk_tokens >= len(ids):
            break
    return out


def _build_index_for_repo(repo_id: str) -> tuple[list[_Chunk], BM25Okapi, int]:
    repo_root = ARTIFACTS / repo_id
    if not repo_root.exists():
        raise FileNotFoundError(
            f"Repo snapshot missing: {repo_root}. Run scripts/snapshot_repos.py."
        )

    chunks: list[_Chunk] = []
    for f in repo_root.rglob("*.py"):
        rel = f.relative_to(repo_root).as_posix()
        if any(p.startswith((".",)) for p in rel.split("/")):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for piece in _chunk_file(
            text,
            chunk_tokens=FROZEN_CONFIG["chunk_tokens"],
            overlap=FROZEN_CONFIG["chunk_overlap_tokens"],
        ):
            chunks.append(
                _Chunk(
                    repo_id=repo_id,
                    file=rel,
                    text=piece,
                    norm_tokens=count_tokens(piece),
                )
            )

    if not chunks:
        raise RuntimeError(f"No chunks built for repo {repo_id}")

    bm25 = BM25Okapi([_tokenize(c.text) for c in chunks])
    build_tokens = sum(c.norm_tokens for c in chunks)
    return chunks, bm25, build_tokens


@dataclass(frozen=True)
class _BM25Payload:
    chunks: list[_Chunk]
    bm25: BM25Okapi


class BM25RagProvider(Provider):
    """Frozen-config BM25 RAG. One index per repo; rebuilt per task only if
    the repo changes (Chunk 4 will memoize)."""

    name = "rag-bm25"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def __init__(self):
        # Index cache: short_id → (chunks, bm25, build_tokens)
        self._cache: dict[str, tuple[list[_Chunk], BM25Okapi, int]] = {}

    def _index(self, repo_id: str):
        if repo_id not in self._cache:
            self._cache[repo_id] = _build_index_for_repo(repo_id)
        return self._cache[repo_id]

    def build(self, task: Task) -> BuildArtifact:
        repo_id = task.meta.get("repo_id")
        if not repo_id:
            raise ValueError(f"task {task.task_id} missing meta.repo_id")
        chunks, bm25, build_tokens = self._index(repo_id)
        return BuildArtifact(
            payload=_BM25Payload(chunks=chunks, bm25=bm25),
            build_tokens_norm=build_tokens,
        )

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        payload: _BM25Payload = artifact.payload  # type: ignore[assignment]
        scores = payload.bm25.get_scores(_tokenize(task.question))
        top_k = FROZEN_CONFIG["top_k"]
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        retrieved = [payload.chunks[i] for i in order]

        context = "\n\n".join(
            f"# file: {c.file}\n{c.text}" for c in retrieved
        )
        prompt = standard_prompt(context=context, question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
