"""Run a single cell end-to-end and print the resulting RunRecord.

Used by `make repro TASK=<id>` to reproduce one row of the results store
on a fresh machine. Token counts in the output should match (within ~1%
per Chunk 4 exit gate #1) the published numbers in
`results/findings/CHUNK_03_findings.md`.

Usage:
    python repro/run_cell.py --task needle-click-0000 \\
        --provider rag-bm25 \\
        --model bedrock.anthropic.claude-sonnet-4-5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenbench.core.env import load_env  # noqa: E402
from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset  # noqa: E402
from tokenbench.judges.auto_contains import AutoContainsJudge  # noqa: E402
from tokenbench.models.anthropic import AnthropicModel  # noqa: E402
from tokenbench.providers.graphify import GraphifyProvider  # noqa: E402
from tokenbench.providers.llmlingua import LLMLinguaProvider  # noqa: E402
from tokenbench.providers.rag import BM25RagProvider  # noqa: E402
from tokenbench.providers.raw_dump import RawDumpProvider  # noqa: E402
from tokenbench.providers.repo_map import RepoMapProvider  # noqa: E402
from tokenbench.results.store import ResultsStore  # noqa: E402
from tokenbench.runner.engine import RunConfig, Runner  # noqa: E402


PROVIDERS = {
    "rag-bm25": BM25RagProvider,
    "raw-dump": RawDumpProvider,
    "repo-map": RepoMapProvider,
    "graphify": GraphifyProvider,
    "llmlingua-rag": LLMLinguaProvider,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="task_id e.g. needle-click-0000")
    ap.add_argument("--provider", default="rag-bm25", choices=sorted(PROVIDERS))
    ap.add_argument("--model", default="bedrock.anthropic.claude-sonnet-4-5")
    ap.add_argument("--out", default=None, help="JSONL store path (default: tmp)")
    args = ap.parse_args(argv[1:])

    load_env()

    dataset = NeedleCodebaseDataset(max_tasks_per_repo=12)
    task = next((t for t in dataset.tasks() if t.task_id == args.task), None)
    if task is None:
        all_ids = [t.task_id for t in dataset.tasks()]
        print(f"unknown task_id: {args.task!r}", file=sys.stderr)
        print(f"available: {all_ids}", file=sys.stderr)
        return 2

    provider = PROVIDERS[args.provider]()
    model = AnthropicModel(args.model)
    judge = AutoContainsJudge()

    out_path = Path(args.out) if args.out else ROOT / "results" / "runs" / "repro.jsonl"
    store = ResultsStore(out_path)
    runner = Runner(store)

    rec = runner.run_cell(task, provider, model, judge, repeat=0, seed=1)

    # Print the record as a single line of JSON for easy diffing.
    print(rec.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
