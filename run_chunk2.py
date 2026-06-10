"""Chunk 2 end-to-end: real Anthropic adapter × BM25 RAG × needle dataset.

This is the P2 exit gate. Two independent runs against the same dataset
must produce numbers that agree within the bootstrap CI of either run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from tokenbench.core.env import load_env
from tokenbench.core.metrics import (
    accuracy,
    bootstrap_ci,
    per_record_tokens,
    summarize,
    tpca_curve,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.anthropic import AnthropicModel
from tokenbench.providers.rag import BM25RagProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner


def _summarize_records(label: str, records: list[RunRecord]) -> dict:
    by_provider: dict[str, list[RunRecord]] = {}
    for r in records:
        by_provider.setdefault(r.provider.name, []).append(r)

    print(f"\n=== {label} ===")
    out = {}
    for name, recs in by_provider.items():
        acc = accuracy(recs)
        curve = tpca_curve(recs)
        per_rec_at_1 = per_record_tokens(recs, V=1)
        dist = summarize(per_rec_at_1)
        ci_low, ci_high = bootstrap_ci(per_rec_at_1)
        print(f"\n  {name}  (n={len(recs)})")
        print(f"    accuracy:               {acc:.3f}")
        for V, val in curve.items():
            print(f"    TPCA(V={V:>5}):           {val:>10.1f}")
        print(
            f"    tokens/cell at V=1: median={dist.median:.0f}  "
            f"IQR=[{dist.q25:.0f}, {dist.q75:.0f}]  "
            f"95% CI(mean)=[{ci_low:.0f}, {ci_high:.0f}]"
        )
        out[name] = {
            "accuracy": acc,
            "tpca_v1": curve[1],
            "tpca_v100": curve[100],
            "tpca_v10k": curve[10_000],
            "tokens_mean_v1": dist.mean,
            "tokens_ci_v1": (ci_low, ci_high),
            "n": len(recs),
        }
    return out


def _reproducibility_check(a: dict, b: dict) -> bool:
    """Each provider's run-A mean tokens must lie inside run-B's bootstrap CI
    (and vice versa). Accuracy must agree within ±0.10 absolute (RAG over
    small N is binary-noisy)."""
    print("\n=== Reproducibility check (run A vs run B) ===")
    ok = True
    for name in a:
        if name not in b:
            print(f"  {name}: MISSING in second run")
            ok = False
            continue
        a_mean = a[name]["tokens_mean_v1"]
        b_lo, b_hi = b[name]["tokens_ci_v1"]
        b_mean = b[name]["tokens_mean_v1"]
        a_lo, a_hi = a[name]["tokens_ci_v1"]
        token_ok = (b_lo <= a_mean <= b_hi) and (a_lo <= b_mean <= a_hi)
        acc_ok = abs(a[name]["accuracy"] - b[name]["accuracy"]) <= 0.10
        flag = "OK" if (token_ok and acc_ok) else "FAIL"
        print(
            f"  {name}: tokens A_mean={a_mean:.0f} in B_CI=[{b_lo:.0f},{b_hi:.0f}]? {token_ok}; "
            f"acc Δ={abs(a[name]['accuracy'] - b[name]['accuracy']):.3f}  [{flag}]"
        )
        ok = ok and token_ok and acc_ok
    return ok


def _plot(records_a: list[RunRecord], records_b: list[RunRecord], out_path: Path):
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for label, records, marker in [("run A", records_a, "o"), ("run B", records_b, "x")]:
        by_p: dict[str, list[RunRecord]] = {}
        for r in records:
            by_p.setdefault(r.provider.name, []).append(r)
        for name, recs in by_p.items():
            ax.scatter(
                sum(per_record_tokens(recs, V=1)) / len(recs),
                accuracy(recs),
                marker=marker,
                s=120,
                label=f"{name} ({label})",
            )
    ax.set_xscale("log")
    ax.set_xlabel("tokens / query (norm, V=1, log)")
    ax.set_ylabel("accuracy")
    ax.set_title("Chunk 2 reproducibility: run A vs run B")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"\nPlot written to {out_path}")


def _run_once(label: str, args, base_seed: int) -> list[RunRecord]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = ResultsStore(out_dir / f"chunk2_{label}.jsonl")
    runner = Runner(store)
    return runner.sweep(
        dataset=NeedleCodebaseDataset(max_tasks_per_repo=args.tasks_per_repo),
        providers=[BM25RagProvider()],
        models=[AnthropicModel(args.model)],
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=args.repeats, base_seed=base_seed),
    )


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-per-repo", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--model", default="bedrock.anthropic.claude-sonnet-4-5")
    ap.add_argument("--out-dir", default="results/runs")
    ap.add_argument("--skip-second-run", action="store_true")
    args = ap.parse_args()

    print(f"Running model={args.model}  tasks_per_repo={args.tasks_per_repo}  repeats={args.repeats}")

    records_a = _run_once("A", args, base_seed=1)
    summary_a = _summarize_records("Run A", records_a)

    if args.skip_second_run:
        return

    records_b = _run_once("B", args, base_seed=2)
    summary_b = _summarize_records("Run B", records_b)

    ok = _reproducibility_check(summary_a, summary_b)
    print(f"\nExit gate: {'PASS' if ok else 'FAIL'}")
    _plot(records_a, records_b, Path(args.out_dir) / "chunk2_repro.png")


if __name__ == "__main__":
    main()
