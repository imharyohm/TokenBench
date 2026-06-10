"""Graphify provider — knowledge-graph context (Path A: real graph cache).

Path A from CHUNK_03 spec: graphs are pre-built out-of-band by the upstream
`graphify` package's AST extractor (no LLM tokens — pure tree-sitter parse)
and cached at `artifacts/graphs/<repo>.json`. The provider reads that cache.

Build to populate the cache (one-shot, run from this repo's .venv):
    cd artifacts/repos/<repo> && graphify update . --no-cluster
    cp artifacts/repos/<repo>/graphify-out/graph.json artifacts/graphs/<repo>.json

Per-query strategy mirrors `graphify query` (references/query.md):
  1. Tokenize question; expand against graph vocabulary (substring + IDF
     match against node labels). No invented tokens.
  2. Seed BFS from the top-K matched nodes.
  3. Pack matched + neighborhood nodes into the prompt under a frozen budget,
     citing source_file:source_location.

Frozen config (DECISIONS.md #6):
- mode: BFS, query expansion enabled
- top_k_seeds: 10 (top scoring nodes seed the traversal)
- bfs_depth: 2
- budget: 3,000 norm tokens (matches skill's default --budget 3000 hint)

Build cost = nodes + links token weight under o200k_base (the deliverable
that's effectively cached). Per-query = packed neighborhood.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from ..core.schemas import Task
from ..core.tokenizer import _encoder, count_tokens
from .base import BuildArtifact, Provider, RetrievedContext
from .prompt_wrapper import standard_prompt

GRAPHS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "graphs"

FROZEN_CONFIG = {
    "graph_source": "graphifyy AST extraction (graphify update --no-cluster)",
    "mode": "bfs",
    "top_k_seeds": 10,
    "bfs_depth": 2,
    "context_token_budget": 3_000,
    "expand_query": True,
}


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def _split_camel_snake(s: str) -> list[str]:
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", s)
    return [p.lower() for p in parts if 3 <= len(p) <= 30]


@dataclass
class _Graph:
    nodes: list[dict]
    links: list[dict]
    by_id: dict[str, dict] = field(default_factory=dict)
    adj: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    label_tokens: dict[str, set[str]] = field(default_factory=dict)
    vocab_idf: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: Path) -> "_Graph":
        data = json.loads(path.read_text())
        g = cls(nodes=data["nodes"], links=data.get("links", []))
        g.by_id = {n["id"]: n for n in g.nodes}
        for e in g.links:
            s, t = e.get("source"), e.get("target")
            if s in g.by_id and t in g.by_id:
                g.adj[s].add(t)
                g.adj[t].add(s)  # undirected traversal
        # Build label tokens + IDF.
        df: dict[str, int] = defaultdict(int)
        for n in g.nodes:
            label = n.get("label", "") or n.get("id", "")
            toks = set(t.lower() for t in _TOKEN_RE.findall(label))
            for t in list(toks):
                toks.update(_split_camel_snake(t))
            toks = {t for t in toks if 3 <= len(t) <= 30}
            g.label_tokens[n["id"]] = toks
            for t in toks:
                df[t] += 1
        N = max(1, len(g.nodes))
        g.vocab_idf = {t: math.log(N / max(1, c)) for t, c in df.items()}
        return g


def _question_tokens(q: str, vocab: set[str]) -> list[str]:
    raw = set(t.lower() for t in _TOKEN_RE.findall(q))
    expanded = set(raw)
    for t in raw:
        expanded.update(_split_camel_snake(t))
    return sorted(t for t in expanded if 3 <= len(t) <= 30 and t in vocab)


def _score_nodes(graph: _Graph, q_tokens: list[str]) -> list[tuple[str, float]]:
    """Score every node by IDF-weighted token overlap with question."""
    if not q_tokens:
        return []
    qset = set(q_tokens)
    scored: list[tuple[str, float]] = []
    for nid, toks in graph.label_tokens.items():
        hit = toks & qset
        if not hit:
            continue
        score = sum(graph.vocab_idf.get(t, 0.0) for t in hit)
        scored.append((nid, score))
    scored.sort(key=lambda x: -x[1])
    return scored


def _bfs_neighborhood(graph: _Graph, seeds: list[str], depth: int) -> list[str]:
    seen = set(seeds)
    order = list(seeds)
    frontier = deque((s, 0) for s in seeds)
    while frontier:
        nid, d = frontier.popleft()
        if d >= depth:
            continue
        for nbr in graph.adj.get(nid, ()):
            if nbr not in seen:
                seen.add(nbr)
                order.append(nbr)
                frontier.append((nbr, d + 1))
    return order


def _render_node(n: dict) -> str:
    label = n.get("label", n.get("id", "?"))
    src = n.get("source_file", "?")
    loc = n.get("source_location", "")
    sep = ":" if loc else ""
    return f"- {label}  ({src}{sep}{loc})"


def _pack_to_budget(graph: _Graph, ordered_ids: list[str], budget: int) -> str:
    enc = _encoder()
    out: list[str] = []
    used = 0
    for nid in ordered_ids:
        n = graph.by_id.get(nid)
        if n is None:
            continue
        line = _render_node(n) + "\n"
        cost = len(enc.encode(line))
        if used + cost > budget:
            break
        out.append(line)
        used += cost
    return "".join(out)


def _build_tokens_for(graph: _Graph) -> int:
    """Estimate the token cost of the cached graph as a deliverable —
    one rendered line per node and edge under the reference encoder. This
    is the amortizable artifact, not the gateway-side token spend (the
    AST extractor used 0 LLM tokens)."""
    enc = _encoder()
    total = 0
    for n in graph.nodes:
        total += len(enc.encode(_render_node(n)))
    for e in graph.links:
        total += len(enc.encode(f"{e.get('source','')}--{e.get('relation','')}->{e.get('target','')}"))
    return total


@dataclass(frozen=True)
class _GraphifyPayload:
    repo_id: str
    graph: _Graph


class GraphifyProvider(Provider):
    """Reads pre-built graph cache; per-query BFS over IDF-matched seeds."""

    name = "graphify"
    version = "0.1.0"
    config = dict(FROZEN_CONFIG)

    def __init__(self):
        self._cache: dict[str, _Graph] = {}
        self._build_tokens_cache: dict[str, int] = {}

    def _graph(self, repo_id: str) -> _Graph:
        if repo_id not in self._cache:
            path = GRAPHS_DIR / f"{repo_id}.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"Graphify cache missing: {path}. Run "
                    f"`cd artifacts/repos/{repo_id} && graphify update . --no-cluster && "
                    f"cp graphify-out/graph.json ../../graphs/{repo_id}.json`."
                )
            self._cache[repo_id] = _Graph.from_json(path)
            self._build_tokens_cache[repo_id] = _build_tokens_for(self._cache[repo_id])
        return self._cache[repo_id]

    def build(self, task: Task) -> BuildArtifact:
        repo_id = task.meta.get("repo_id")
        if not repo_id:
            raise ValueError(f"task {task.task_id} missing meta.repo_id")
        graph = self._graph(repo_id)
        return BuildArtifact(
            payload=_GraphifyPayload(repo_id=repo_id, graph=graph),
            build_tokens_norm=self._build_tokens_cache[repo_id],
        )

    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        payload: _GraphifyPayload = artifact.payload  # type: ignore[assignment]
        graph = payload.graph
        vocab = set(graph.vocab_idf.keys())
        q_tokens = _question_tokens(task.question, vocab) if FROZEN_CONFIG["expand_query"] else []
        scored = _score_nodes(graph, q_tokens)
        seeds = [nid for nid, _ in scored[: FROZEN_CONFIG["top_k_seeds"]]]
        ordered = _bfs_neighborhood(graph, seeds, FROZEN_CONFIG["bfs_depth"])
        body = _pack_to_budget(graph, ordered, FROZEN_CONFIG["context_token_budget"])
        if not body:
            body = "(graph traversal returned no matching nodes)"
        prompt = standard_prompt(context=body, question=task.question)
        return RetrievedContext(text=prompt, input_tokens_norm=count_tokens(prompt))
