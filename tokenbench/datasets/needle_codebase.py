"""Needle-in-codebase dataset, built from pinned repo snapshots.

For each pinned repo, we walk the source tree, parse Python files with the
stdlib `ast` module, and emit one task per top-level function/method that
has a non-trivial docstring. The task asks "which function/method <does X>?"
where <X> is the first sentence of the docstring; the gold answer is the
qualified symbol name.

Auto-scored via AutoContainsJudge — zero judge risk for Chunk 2.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..core.schemas import RepoRef, Task
from .base import Dataset
from .repo_pins import REPO_PINS, RepoPin

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS = _PROJECT_ROOT / "artifacts" / "repos"
_DOCKER_DIGESTS = _PROJECT_ROOT / "artifacts" / "docker" / "digests.json"


def _load_docker_digests() -> dict[str, str]:
    """Read artifacts/docker/digests.json if present.

    Maps short_id -> image_id. Returns {} if the file doesn't exist yet
    (i.e. images haven't been built — Task.repo.docker_image stays None).
    """
    if not _DOCKER_DIGESTS.exists():
        return {}
    blob = json.loads(_DOCKER_DIGESTS.read_text())
    return {e["short_id"]: e["image_id"] for e in blob.get("images", [])}

# Symbols that aren't useful as needles even if they have docstrings.
_BORING_NAMES = {"__init__", "__repr__", "__str__", "__eq__", "__hash__",
                 "__call__", "__getitem__", "__setitem__", "__len__",
                 "main", "setup"}


@dataclass(frozen=True)
class _SymbolHit:
    repo_id: str
    file: str
    qualified: str  # e.g. "rich.console.Console.print"
    short: str      # e.g. "print"
    summary: str    # first sentence of docstring


def _summary_first_sentence(doc: str) -> str:
    text = " ".join(doc.strip().split())
    # crude: split on the first period followed by space
    for sep in [". ", ".\n", "? ", "! "]:
        idx = text.find(sep)
        if 0 < idx < 200:
            return text[: idx + 1].strip()
    return text[:200].strip()


def _walk_python_files(root: Path) -> Iterator[Path]:
    for f in root.rglob("*.py"):
        rel = f.relative_to(root).as_posix()
        if any(part.startswith((".", "_test", "test_")) for part in rel.split("/")):
            continue
        if "tests/" in rel or rel.startswith("docs/"):
            continue
        yield f


def _extract_hits(repo_id: str, root: Path, max_per_repo: int) -> list[_SymbolHit]:
    hits: list[_SymbolHit] = []
    for f in _walk_python_files(root):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        rel = f.relative_to(root).as_posix()
        module_dotted = rel[:-3].replace("/", ".")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if name.startswith("_") or name in _BORING_NAMES:
                    continue
                doc = ast.get_docstring(node) or ""
                if len(doc.strip()) < 30:
                    continue
                qualified = f"{module_dotted}.{name}"
                hits.append(
                    _SymbolHit(
                        repo_id=repo_id,
                        file=rel,
                        qualified=qualified,
                        short=name,
                        summary=_summary_first_sentence(doc),
                    )
                )
                if len(hits) >= max_per_repo:
                    return hits
    return hits


class NeedleCodebaseDataset(Dataset):
    """Generates Tasks by parsing pinned repo snapshots.

    The needle is the function's *short name* — the model only needs to
    surface the right symbol, regardless of which module path the retriever
    produced. This is what the `auto_contains` scorer checks.
    """

    name = "needle-codebase"
    dataset_version = "1.0.0"

    def __init__(self, *, max_tasks_per_repo: int = 6, repos: list[RepoPin] | None = None):
        self.max_tasks_per_repo = max_tasks_per_repo
        self.repos = repos if repos is not None else REPO_PINS

    def tasks(self) -> Iterator[Task]:
        digests = _load_docker_digests()
        idx = 0
        for pin in self.repos:
            repo_root = ARTIFACTS / pin.short_id
            if not repo_root.exists():
                raise FileNotFoundError(
                    f"Repo snapshot missing: {repo_root}. Run scripts/snapshot_repos.py first."
                )
            hits = _extract_hits(pin.short_id, repo_root, self.max_tasks_per_repo)
            for hit in hits:
                yield Task(
                    task_id=f"needle-{pin.short_id}-{idx:04d}",
                    dataset_version=self.dataset_version,
                    task_type="needle_function",
                    question=(
                        f"In the {pin.short_id} codebase, which function "
                        f"is described as: \"{hit.summary}\"? "
                        "Answer with just the function name."
                    ),
                    repo=RepoRef(
                        url=pin.url,
                        commit=pin.commit,
                        snapshot_sha256=pin.snapshot_sha256,
                        docker_image=digests.get(pin.short_id),
                    ),
                    gold=hit.short,
                    needle=hit.short,
                    scoring="auto_contains",
                    canary="TOKENBENCH-CANARY-needle-codebase-1.0.0",
                    license=pin.license,
                    meta={
                        "language": pin.language,
                        "repo_id": pin.short_id,
                        "file": hit.file,
                        "qualified": hit.qualified,
                    },
                )
                idx += 1
