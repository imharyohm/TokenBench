"""Generate candidate answers for SWE-QA tasks (Chunk 5 deliverable 3 prep).

Runs one (provider, model) over the SWE-QA dataset and writes one candidate
answer per task to artifacts/swe_qa/v<version>/candidates.jsonl. Idempotent:
skips task_ids already present.

Defaults to rag-bm25 + sonnet-4-5 — the locked headline pair, cheapest path.

The candidates are the substrate for the human gold-set labels (DECISIONS.md
#11): you read each (question, reference, candidate) triple and label it
pass/fail. The labels are committed to git BEFORE any judge run.

Output schema:
    {"task_id": ...,
     "candidate": "<model output text>",
     "source": "<provider_name>/<model_name>",
     "input_tokens_norm": int,
     "output_tokens_norm": int,
     "latency_ms": int,
     "timestamp": ISO-8601}

CLI:
    python scripts/generate_swe_qa_candidates.py \
        --version 1.0.0 \
        --provider rag-bm25 \
        --model bedrock.anthropic.claude-sonnet-4-5 \
        [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tokenbench.core.env import load_env  # noqa: E402
from tokenbench.datasets.swe_qa import QUESTIONS_DIR, SweQaDataset  # noqa: E402
from tokenbench.models.anthropic import AnthropicModel  # noqa: E402
from tokenbench.providers.prompt_wrapper import freeform_prompt  # noqa: E402
from tokenbench.providers.rag import BM25RagProvider  # noqa: E402

PROVIDERS = {"rag-bm25": BM25RagProvider}


def already_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                rec = json.loads(line)
                out.add(rec["task_id"])
    return out


def append_record(path: Path, rec: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--provider", default="rag-bm25", choices=list(PROVIDERS))
    p.add_argument("--model", default="bedrock.anthropic.claude-sonnet-4-5")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N tasks (for smoke tests)")
    p.add_argument("--max-tokens", type=int, default=600,
                   help="Max output tokens per candidate (free-form ~3-7 sentences)")
    args = p.parse_args()
    load_env()

    candidates_path = QUESTIONS_DIR / f"v{args.version}" / "candidates.jsonl"
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    done = already_done(candidates_path)
    print(f"Already done: {len(done)} task(s) in {candidates_path}")

    dataset = SweQaDataset(version=args.version)
    tasks = list(dataset)
    print(f"Loaded {len(tasks)} SWE-QA tasks (version={args.version})")

    provider_cls = PROVIDERS[args.provider]
    provider = provider_cls()
    model = AnthropicModel(args.model)
    source = f"{args.provider}/{args.model}"

    todo = [t for t in tasks if t.task_id not in done]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print("Nothing to generate; exiting.")
        return
    print(f"Generating {len(todo)} candidate(s) using {source}")

    # Build artifact cache by (provider, repo_id) — prov.build is by-task,
    # but free-form rag-bm25 only depends on repo_id so we cache here too.
    artifact_cache: dict[str, object] = {}

    t0 = time.time()
    spent_input_tokens = 0
    spent_output_tokens = 0
    for i, task in enumerate(todo, start=1):
        repo_id = task.meta["repo_id"]
        if repo_id not in artifact_cache:
            artifact_cache[repo_id] = provider.build(task)
        artifact = artifact_cache[repo_id]

        # Reuse provider's retrieval but swap the prompt to the free-form one.
        # The standard retrieve() builds a needle-style prompt; we re-render
        # with freeform_prompt so the model produces 3-7 sentences instead of
        # a bare symbol name.
        retrieved = provider.retrieve(task, artifact)
        # retrieved.text is the standard prompt; pull the context out by
        # slicing between <context>...</context>.
        ctx_start = retrieved.text.find("<context>\n") + len("<context>\n")
        ctx_end = retrieved.text.find("\n</context>")
        if ctx_start < 0 or ctx_end < 0:
            raise RuntimeError(f"unexpected prompt shape from {args.provider}")
        context = retrieved.text[ctx_start:ctx_end]
        prompt = freeform_prompt(context=context, question=task.question)

        resp = model.complete(prompt, max_tokens=args.max_tokens, seed=0)
        spent_input_tokens += resp.norm_input_tokens
        spent_output_tokens += resp.norm_output_tokens

        rec = {
            "task_id": task.task_id,
            "candidate": resp.text,
            "source": source,
            "input_tokens_norm": resp.norm_input_tokens,
            "output_tokens_norm": resp.norm_output_tokens,
            "latency_ms": resp.latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        append_record(candidates_path, rec)
        if i % 10 == 0 or i == len(todo):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(
                f"  [{i:3d}/{len(todo)}] {task.task_id} "
                f"in_tok={resp.norm_input_tokens} out_tok={resp.norm_output_tokens} "
                f"({rate:.2f} tasks/s, ~{(len(todo) - i) / rate:.0f}s remaining)"
            )

    print()
    print(f"Done. Wrote → {candidates_path}")
    print(f"  cumulative input_tokens_norm:  {spent_input_tokens:,}")
    print(f"  cumulative output_tokens_norm: {spent_output_tokens:,}")
    print(f"  wall time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
