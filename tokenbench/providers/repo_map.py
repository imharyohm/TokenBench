"""Repo-map provider — aider-style symbol map (faithful, not literal).

Background: Aider's `repomap` package is the reference implementation. It
can't install on Python 3.14 (its old numpy dep imports the removed
`pkgutil.ImpImporter`). We implement the same approach here directly on
tree-sitter:

  1. Parse every Python file with tree-sitter.
  2. Extract top-level definitions (functions, classes, methods) with their
     signatures and docstring first sentences.
  3. Rank files by reference centrality (PageRank over identifier mentions
     across files).
  4. Pack the ranked symbols into the prompt under a frozen token budget.

Frozen config (DECISIONS.md #6) records `provenance: aider-style` so the
deviation from the upstream package is auditable.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core.schemas import Task
from ..core.tokenizer import _encoder, count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import standard_prompt

ARTIFACTS = Path(__file__).resolve().parent.parent.parent / "artifacts" / "repos"

FROZEN_CONFIG = {
    "context_token_budget": 8_000,
    "provenance": "aider-style (not aider-chat package; Py3.14 incompat)",
    "ranker": "pagerank_over_symbol_refs",
    "summary_chars": 120,
}

_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


@dataclass(frozen=True)
class _Sym:
    file: str
    kind: str  # "def" | "class" | "method"
    name: str
    signature: str
    summary: str  # first sentence of docstring


@dataclass(frozen=True)
class _RepoMap:
    repo_id: str
    rendered: str
    rendered_norm_tokens: int


def _summary(doc: str | None, limit: int) -> str:
    if not doc:
        return ""
    text = " ".join(doc.strip().split())
    for sep in [". ", ".\n", "? ", "! "]:
        idx = text.find(sep)
        if 0 < idx < limit:
            return text[: idx + 1]
    return text[:limit]


def _signature(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args]
        return f"def {node.name}({', '.join(args)})"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return ""


def _extract_symbols(repo_root: Path) -> tuple[list[_Sym], dict[str, set[str]]]:
    """Returns (symbols, references). references[file] = set of identifiers
    used by that file (the basis for the centrality graph)."""
    symbols: list[_Sym] = []
    references: dict[str, set[str]] = {}
    for f in sorted(repo_root.rglob("*.py")):
        rel = f.relative_to(repo_root).as_posix()
        if any(p.startswith(".") for p in rel.split("/")):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    _Sym(rel, "def", node.name, _signature(node),
                         _summary(ast.get_docstring(node), FROZEN_CONFIG["summary_chars"]))
                )
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    _Sym(rel, "class", node.name, _signature(node),
                         _summary(ast.get_docstring(node), FROZEN_CONFIG["summary_chars"]))
                )
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name.startswith("_"):
                            continue
                        symbols.append(
                            _Sym(rel, "method", f"{node.name}.{child.name}",
                                 f"def {node.name}.{child.name}({', '.join(a.arg for a in child.args.args)})",
                                 _summary(ast.get_docstring(child), FROZEN_CONFIG["summary_chars"]))
                        )

        references[rel] = set(_IDENT_RE.findall(src))

    return symbols, references


def _pagerank(adj: dict[str, list[str]], damping: float = 0.85, iters: int = 30) -> dict[str, float]:
    nodes = list(adj.keys())
    n = len(nodes)
    if n == 0:
        return {}
    idx = {nm: i for i, nm in enumerate(nodes)}
    M = np.zeros((n, n))
    for src, dsts in adj.items():
        if not dsts:
            continue
        w = 1.0 / len(dsts)
        for d in dsts:
            if d in idx:
                M[idx[d], idx[src]] += w
    rank = np.full(n, 1.0 / n)
    teleport = np.full(n, (1.0 - damping) / n)
    for _ in range(iters):
        rank = damping * (M @ rank) + teleport
    return {nodes[i]: float(rank[i]) for i in range(n)}


def _build_repo_map(repo_id: str) -> _RepoMap:
    repo_root = ARTIFACTS / repo_id
    if not repo_root.exists():
        raise FileNotFoundError(
            f"Repo snapshot missing: {repo_root}. Run scripts/snapshot_repos.py."
        )

    symbols, references = _extract_symbols(repo_root)

    # Build file-symbol bipartite reference graph: file -> files whose
    # exported names this file mentions. Mirrors aider's approach.
    name_to_files: dict[str, set[str]] = defaultdict(set)
    for s in symbols:
        name_to_files[s.name.split(".")[0]].add(s.file)
    adj: dict[str, list[str]] = {f: [] for f in references}
    for f, idents in references.items():
        seen: set[str] = set()
        for ident in idents:
            for tgt in name_to_files.get(ident, ()):
                if tgt != f and tgt not in seen:
                    adj[f].append(tgt)
                    seen.add(tgt)

    file_rank = _pagerank(adj)

    # Order symbols by host-file rank, stable within a file by source order.
    symbols_sorted = sorted(
        symbols,
        key=lambda s: (-file_rank.get(s.file, 0.0), s.file, s.name),
    )

    # Pack into budget.
    enc = _encoder()
    budget = FROZEN_CONFIG["context_token_budget"]
    out_parts: list[str] = []
    cur_file: str | None = None
    used = 0
    for s in symbols_sorted:
        if s.file != cur_file:
            line = f"\n# file: {s.file}\n"
            out_parts.append(line)
            used += len(enc.encode(line))
            cur_file = s.file
        line = f"  {s.signature}"
        if s.summary:
            line += f"  — {s.summary}"
        line += "\n"
        cost = len(enc.encode(line))
        if used + cost > budget:
            break
        out_parts.append(line)
        used += cost

    rendered = "".join(out_parts).lstrip()
    return _RepoMap(repo_id=repo_id, rendered=rendered, rendered_norm_tokens=count_tokens(rendered))


@dataclass(frozen=True)
class _RepoMapPayload:
    repo_id: str
    rendered: str


class RepoMapProvider(Provider):
    """Aider-style repo-map. Frozen 8k-token budget. PageRank over symbol refs.

    Build cost = the rendered map's tokens (we read every file and rank;
    the deliverable that gets cached is the symbol map itself).
    """

    name = "repo-map"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def __init__(self):
        self._cache: dict[str, _RepoMap] = {}

    def _map(self, repo_id: str) -> _RepoMap:
        if repo_id not in self._cache:
            self._cache[repo_id] = _build_repo_map(repo_id)
        return self._cache[repo_id]

    def build(self, task: Task) -> BuildArtifact:
        repo_id = task.meta.get("repo_id")
        if not repo_id:
            raise ValueError(f"task {task.task_id} missing meta.repo_id")
        rm = self._map(repo_id)
        return BuildArtifact(
            payload=_RepoMapPayload(repo_id=repo_id, rendered=rm.rendered),
            build_tokens_norm=rm.rendered_norm_tokens,
        )

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        payload: _RepoMapPayload = artifact.payload  # type: ignore[assignment]
        prompt = standard_prompt(context=payload.rendered, question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
