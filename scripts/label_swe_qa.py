"""Interactive human-labeling helper for SWE-QA gold set (Chunk 5 deliverable 3).

Walks you through (question, reference, candidate) triples and writes
pass/fail labels to artifacts/swe_qa/v<version>/human_labels.jsonl.

Output schema (one JSON-per-line, append-only, idempotent skip on task_id):
    {"task_id":     ...,
     "label":       "pass" | "fail",
     "annotator_id": ...,
     "timestamp":    ISO-8601 UTC,
     "rationale":    "<optional one-liner>",
     "candidate_source": "<provider>/<model>",
     "is_retest":   false}   # for the test-retest sub-sample (DECISIONS.md #11)

Pre-registration (DECISIONS.md #11, Chunk 5 exit gate 4):
    Labels are written to git BEFORE any LLM judge call.
    No relabeling after seeing judge outputs. Period.

Test-retest sub-sample:
    Use --retest <task_id> to re-label a single task. The original label is
    preserved; the new label is written to human_labels_retest.jsonl with
    is_retest=True. Cohen's κ between first-pass and retest labels gives a
    within-rater stability estimate (proxy for inter-rater).

CLI:
    python scripts/label_swe_qa.py --annotator hgupta163
    python scripts/label_swe_qa.py --annotator hgupta163 --retest swe-click-0042
    python scripts/label_swe_qa.py --annotator hgupta163 --resume   # skip done
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tokenbench.datasets.swe_qa import QUESTIONS_DIR, SweQaDataset  # noqa: E402

LABELS_FILENAME = "human_labels.jsonl"
RETEST_FILENAME = "human_labels_retest.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(json.loads(line))
    return out


def _candidates_by_id(version: str) -> dict[str, dict]:
    cpath = QUESTIONS_DIR / f"v{version}" / "candidates.jsonl"
    if not cpath.exists():
        sys.exit(
            f"ERROR: {cpath} not found.\n"
            "Run scripts/generate_swe_qa_candidates.py first."
        )
    return {rec["task_id"]: rec for rec in _load_jsonl(cpath)}


def _print_triple(task, candidate_rec: dict, idx: int, total: int):
    print()
    print("=" * 78)
    print(f"  [{idx:3d}/{total}]  {task.task_id}    "
          f"repo={task.meta['repo_id']}  difficulty={task.meta.get('difficulty', '?')}")
    print("=" * 78)
    print()
    print("QUESTION:")
    print(_wrap(task.question, 76, indent=2))
    print()
    print("REFERENCE (gold):")
    print(_wrap(task.gold, 76, indent=2))
    print()
    print(f"CANDIDATE  (source: {candidate_rec['source']}):")
    print(_wrap(candidate_rec["candidate"], 76, indent=2))
    print()


def _wrap(text: str, width: int, indent: int = 0) -> str:
    import textwrap
    pad = " " * indent
    out_lines: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out_lines.append("")
            continue
        out_lines.extend(textwrap.wrap(para, width=width,
                                       initial_indent=pad, subsequent_indent=pad)
                         or [pad])
    return "\n".join(out_lines)


def _prompt_label() -> tuple[str | None, str]:
    while True:
        try:
            raw = input("Label [p=pass, f=fail, s=skip, q=quit]"
                        " (then optional rationale after a space): ").strip()
        except EOFError:
            return None, ""
        if not raw:
            continue
        head = raw[0].lower()
        rationale = raw[2:].strip() if len(raw) > 2 else ""
        if head == "p":
            return "pass", rationale
        if head == "f":
            return "fail", rationale
        if head == "s":
            return None, rationale
        if head == "q":
            print("\nQuit. Labels written so far are persisted.")
            sys.exit(0)
        print("  unrecognized; type p / f / s / q")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--annotator", required=True,
                   help="Annotator identifier (typically your username/handle)")
    p.add_argument("--retest", default=None,
                   help="Re-label a specific task_id for test-retest κ; writes "
                        "to human_labels_retest.jsonl")
    p.add_argument("--resume", action="store_true",
                   help="Skip already-labeled tasks (default: prompt-overwrite confirm)")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N labels this session")
    args = p.parse_args()

    candidates = _candidates_by_id(args.version)
    tasks = {t.task_id: t for t in SweQaDataset(version=args.version)}

    common_ids = sorted(set(tasks) & set(candidates))
    if not common_ids:
        sys.exit("ERROR: no tasks have candidates yet")

    labels_path = QUESTIONS_DIR / f"v{args.version}" / LABELS_FILENAME
    retest_path = QUESTIONS_DIR / f"v{args.version}" / RETEST_FILENAME
    out_path = retest_path if args.retest else labels_path

    existing = _load_jsonl(out_path)
    done = {rec["task_id"] for rec in existing}

    if args.retest:
        if args.retest not in tasks:
            sys.exit(f"ERROR: --retest task_id {args.retest!r} not in dataset")
        targets = [args.retest]
    else:
        targets = [tid for tid in common_ids
                   if not args.resume or tid not in done]

    if args.limit:
        targets = targets[: args.limit]

    print()
    print(f"  annotator      : {args.annotator}")
    print(f"  dataset        : v{args.version}")
    print(f"  output         : {out_path}")
    print(f"  total tasks    : {len(common_ids)}")
    print(f"  already done   : {len(done)}")
    print(f"  this session   : {len(targets)}")
    print(f"  retest mode    : {'yes (' + args.retest + ')' if args.retest else 'no'}")
    print()
    print("  Labels are pre-registered: do NOT relabel after seeing judge outputs.")
    print()

    written = 0
    for i, tid in enumerate(targets, start=1):
        task = tasks[tid]
        cand = candidates[tid]
        _print_triple(task, cand, i, len(targets))
        label, rationale = _prompt_label()
        if label is None:
            print(f"  → skipped {tid}")
            continue
        rec = {
            "task_id": tid,
            "label": label,
            "annotator_id": args.annotator,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rationale": rationale,
            "candidate_source": cand["source"],
            "is_retest": bool(args.retest),
        }
        with out_path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
        print(f"  → wrote {label.upper()} for {tid}  (session: {written})")

    print()
    print(f"Done. Wrote {written} new label(s) to {out_path}")


if __name__ == "__main__":
    main()
