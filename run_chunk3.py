"""Chunk 3 sweep: 5 providers × 2 models × needle dataset.

Provider lineup (all behind providers/base.py, all using prompt_wrapper):
  - raw-dump      naive baseline (truncate to 80k token budget)
  - rag-bm25      Chunk 2's reproducible reference
  - repo-map      aider-style symbol map under 8k budget
  - graphify      pre-built graph (Path A) + BFS over IDF-matched seeds
  - llmlingua-rag LLMLingua-2 compression composed on BM25 RAG @ 0.5 ratio

Models (both via the Anthropic-format gateway, single adapter):
  - bedrock.anthropic.claude-sonnet-4-5
  - openai.gpt-4o-mini

Outputs:
  - results/runs/chunk3.jsonl                — append-only run records
  - results/runs/chunk3_pareto.png           — accuracy vs tokens/V Pareto
  - results/runs/chunk3_amortization.png     — TPCA-vs-V on log-x per provider
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from tokenbench.core.env import load_env
from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    accuracy,
    bootstrap_ci,
    per_record_tokens,
    summarize,
    tpca,
    tpca_curve,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.anthropic import AnthropicModel
from tokenbench.providers.graphify import GraphifyProvider
from tokenbench.providers.llmlingua import LLMLinguaProvider
from tokenbench.providers.rag import BM25RagProvider
from tokenbench.providers.raw_dump import RawDumpProvider
from tokenbench.providers.repo_map import RepoMapProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner, cells_count


PROVIDER_FACTORIES = [
    ("rag-bm25", BM25RagProvider),
    ("repo-map", RepoMapProvider),
    ("graphify", GraphifyProvider),
    ("llmlingua-rag", LLMLinguaProvider),
    ("raw-dump", RawDumpProvider),
]

MODELS = [
    "bedrock.anthropic.claude-sonnet-4-5",
    "openai.gpt-4o-mini",
]


def _summarize(records: list[RunRecord]) -> None:
    by_pm: dict[tuple[str, str], list[RunRecord]] = {}
    for r in records:
        by_pm.setdefault((r.provider.name, r.model), []).append(r)

    print("\n=== Chunk 3 sweep summary ===")
    print(f"{'provider':16s} {'model':36s} {'n':>3} {'acc':>6} "
          f"{'TPCA(V=1)':>12} {'TPCA(V=100)':>12} {'TPCA(V=10k)':>12}  med tok/cell")
    for (pname, mname), recs in sorted(by_pm.items()):
        acc = accuracy(recs)
        curve = tpca_curve(recs)
        per_v1 = per_record_tokens(recs, V=1)
        med = summarize(per_v1).median
        print(f"{pname:16s} {mname:36s} {len(recs):>3} {acc:>6.3f} "
              f"{curve[1]:>12.0f} {curve[100]:>12.0f} {curve[10_000]:>12.0f}  {med:>12.0f}")


def _plot_pareto(records: list[RunRecord], out_path: Path, V: int = 100) -> None:
    by_pm: dict[tuple[str, str], list[RunRecord]] = {}
    for r in records:
        by_pm.setdefault((r.provider.name, r.model), []).append(r)

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    markers = {MODELS[0]: "o", MODELS[1]: "x"}
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    color_for: dict[str, tuple] = {}
    for i, (pn, _) in enumerate(PROVIDER_FACTORIES):
        color_for[pn] = colors[i]

    for (pname, mname), recs in by_pm.items():
        per = per_record_tokens(recs, V=V)
        acc = accuracy(recs)
        ax.scatter(
            np.mean(per),
            acc,
            marker=markers.get(mname, "s"),
            s=140,
            color=color_for[pname],
            edgecolors="black",
            linewidths=0.6,
            label=f"{pname} / {mname.split('.')[-1]}",
        )
    ax.set_xscale("log")
    ax.set_xlabel(f"mean tokens / cell at V={V} (log)")
    ax.set_ylabel("accuracy")
    ax.set_title(f"Chunk 3 Pareto: accuracy vs tokens (V={V})")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7, loc="lower right", ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"  Pareto plot → {out_path}")


def _plot_amortization(records: list[RunRecord], out_path: Path) -> None:
    by_provider: dict[str, list[RunRecord]] = {}
    for r in records:
        # Aggregate across both models for a per-method amortization curve.
        by_provider.setdefault(r.provider.name, []).append(r)

    Vs = np.logspace(0, 4.5, 30)
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    for pname, recs in sorted(by_provider.items()):
        ys = []
        for V in Vs:
            try:
                ys.append(tpca(recs, V=float(V)))
            except Exception:
                ys.append(np.nan)
        ax.plot(Vs, ys, label=pname, linewidth=2)
    for V in DEFAULT_AMORTIZATION_VOLUMES:
        ax.axvline(V, color="grey", linestyle=":", alpha=0.35)
        ax.text(V, ax.get_ylim()[1], f" V={V}", fontsize=7, va="top")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("amortization volume V (log)")
    ax.set_ylabel("TPCA (tokens per correct answer, log)")
    ax.set_title("Chunk 3 amortization curves — TPCA(V) per provider")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"  Amortization plot → {out_path}")


def _exit_gate_byte_identical_tasks(records: list[RunRecord]) -> bool:
    """Exit gate #1: swapping provider changes only token/accuracy; task and
    model are byte-identical across runs.

    We verify by checking the (task_id × model × repeat) -> (provider) tuple:
    every distinct (task, model, repeat) triple appears EXACTLY once per
    provider, with no missing combinations.
    """
    provider_names = sorted({r.provider.name for r in records})
    triples = sorted({(r.task_id, r.model, r.repeat) for r in records})
    expected = set(provider_names)
    ok = True
    missing_examples = []
    for t in triples:
        seen = {r.provider.name for r in records
                if (r.task_id, r.model, r.repeat) == t}
        if seen != expected:
            ok = False
            missing_examples.append((t, expected - seen))
            if len(missing_examples) >= 3:
                break
    print(f"\n  Exit gate #1 (task×model×repeat byte-identical across providers): "
          f"{'PASS' if ok else 'FAIL'}")
    if not ok:
        for t, miss in missing_examples:
            print(f"    {t} missing providers: {miss}")
    return ok


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-per-repo", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--out-dir", default="results/runs")
    ap.add_argument(
        "--providers",
        nargs="*",
        default=None,
        help="Optional subset of provider names; default = all.",
    )
    ap.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Optional subset of model names; default = both.",
    )
    args = ap.parse_args()

    providers = [
        cls() for name, cls in PROVIDER_FACTORIES
        if args.providers is None or name in args.providers
    ]
    models = [
        AnthropicModel(m) for m in MODELS
        if args.models is None or m in args.models
    ]

    dataset = NeedleCodebaseDataset(max_tasks_per_repo=args.tasks_per_repo)
    n_tasks = sum(1 for _ in dataset.tasks())
    cells = cells_count(n_tasks, len(providers), len(models), args.repeats)
    print(f"Sweep plan: {n_tasks} tasks × {len(providers)} providers "
          f"× {len(models)} models × {args.repeats} repeats = {cells} cells")
    print(f"Providers: {[p.name for p in providers]}")
    print(f"Models: {[m.name for m in models]}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = ResultsStore(out_dir / "chunk3.jsonl")
    runner = Runner(store)

    skipped: list = []
    new_records = runner.sweep(
        dataset=dataset,
        providers=providers,
        models=models,
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=args.repeats, base_seed=1),
        on_skip=skipped.append,
    )
    if skipped:
        print(f"  (idempotent skip: {len(skipped)} cell(s) already in store)")

    # Summarise the full store filtered to this sweep's selection — so a
    # resumed sweep prints the same table as a clean one.
    selected_providers = {p.name for p in providers}
    selected_models = {m.name for m in models}
    records = [
        r for r in store.all()
        if r.provider.name in selected_providers
        and r.model in selected_models
        and r.dataset_version == dataset.dataset_version
        and r.repeat < args.repeats
    ]
    _ = new_records  # kept for downstream debugging hooks

    _summarize(records)
    _exit_gate_byte_identical_tasks(records)
    _plot_pareto(records, out_dir / "chunk3_pareto.png", V=100)
    _plot_amortization(records, out_dir / "chunk3_amortization.png")


if __name__ == "__main__":
    main()
