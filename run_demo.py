"""Chunk 1 end-to-end demo (mocks only).

Runs three mock providers (raw / RAG / Graphify) × one mock model × one
mock dataset, computes TPCA at V ∈ {1, 100, 10000}, and plots the
accuracy-vs-tokens Pareto frontier per V.

This is the P1 exit gate: every later chunk plugs into the same shape.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    ParetoPoint,
    accuracy,
    bootstrap_ci,
    pareto_frontier,
    per_record_tokens,
    summarize,
    tpca_curve,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.mock import MockDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.mock import MockModel
from tokenbench.providers.mock import (
    MockGraphifyProvider,
    MockRAGProvider,
    MockRawProvider,
)
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner


def _records_by_provider(records: list[RunRecord]) -> dict[str, list[RunRecord]]:
    out: dict[str, list[RunRecord]] = {}
    for r in records:
        out.setdefault(r.provider.name, []).append(r)
    return out


def _print_summary(records: list[RunRecord]) -> None:
    by_provider = _records_by_provider(records)
    print("\n=== Per-provider summary ===")
    for name, recs in by_provider.items():
        acc = accuracy(recs)
        curve = tpca_curve(recs)
        per_rec_at_1 = per_record_tokens(recs, V=1)
        dist = summarize(per_rec_at_1)
        ci_low, ci_high = bootstrap_ci(per_rec_at_1)
        print(f"\n  {name}  (n={len(recs)})")
        print(f"    accuracy:      {acc:.3f}")
        for V, val in curve.items():
            print(f"    TPCA(V={V:>5}): {val:>10.1f}")
        print(
            f"    tokens/cell at V=1:  median={dist.median:.0f}  "
            f"IQR=[{dist.q25:.0f}, {dist.q75:.0f}]  "
            f"95% CI(mean)=[{ci_low:.0f}, {ci_high:.0f}]"
        )


def _plot_pareto(
    records: list[RunRecord],
    *,
    out_path: Path,
    volumes=DEFAULT_AMORTIZATION_VOLUMES,
) -> None:
    by_provider = _records_by_provider(records)

    fig, axes = plt.subplots(1, len(volumes), figsize=(4.5 * len(volumes), 4), sharey=True)
    if len(volumes) == 1:
        axes = [axes]

    for ax, V in zip(axes, volumes):
        points = []
        for name, recs in by_provider.items():
            acc = accuracy(recs)
            tokens_mean = sum(per_record_tokens(recs, V=V)) / len(recs)
            points.append(ParetoPoint(method=name, accuracy=acc, tokens_per_query=tokens_mean))

        frontier = {p.method for p in pareto_frontier(points)}

        for p in points:
            on_frontier = p.method in frontier
            ax.scatter(
                p.tokens_per_query,
                p.accuracy,
                s=140 if on_frontier else 70,
                edgecolor="black" if on_frontier else "gray",
                linewidth=2 if on_frontier else 1,
                label=p.method,
                zorder=3,
            )
            ax.annotate(
                p.method,
                (p.tokens_per_query, p.accuracy),
                xytext=(6, 6),
                textcoords="offset points",
                fontsize=9,
            )
        ax.set_xscale("log")
        ax.set_xlabel("tokens / query (norm, log)")
        ax.set_title(f"V = {V}")
        ax.grid(True, which="both", alpha=0.3)

    axes[0].set_ylabel("accuracy")
    fig.suptitle("TokenBench (mocks) — Accuracy vs normalized tokens by amortization V")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"\nPareto plot written to {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-tasks", type=int, default=20)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out-dir", default="results/runs")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = ResultsStore(out_dir / "demo_runs.jsonl")

    runner = Runner(store)
    records = runner.sweep(
        dataset=MockDataset(n_tasks=args.n_tasks),
        providers=[
            MockRawProvider(),
            MockRAGProvider(),
            MockGraphifyProvider(),
        ],
        models=[MockModel(correctness_rate=0.85, output_token_budget=8)],
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=args.repeats, base_seed=42),
    )

    print(f"\nWrote {len(records)} run records to {store.path}")
    _print_summary(records)
    _plot_pareto(records, out_path=out_dir / "pareto.png")


if __name__ == "__main__":
    main()
