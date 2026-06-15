"""Chunk 6 deliverable C — statistical rigor sweep.

Two-pass sweep over BOTH needle (auto-scored) and SWE-QA (LLM-judged)
datasets at 3 repeats per cell, with task-level bootstrap CIs.

Scope F (locked 2026-06-13 with the user, ~$50):
  - needle: 24 tasks (max_tasks_per_repo=8 across 3 pinned repos)
  - swe_qa: 30 stratified-sample tasks (sample_chunk6.jsonl)
  - providers: rag-bm25, repo-map, graphify, llmlingua-rag (always);
                raw-dump on needle only (its $300+ SWE-QA bill is
                Pareto-dominated and adds no information).
  - models: bedrock.anthropic.claude-sonnet-4-5, openai.gpt-4o-mini
  - repeats: 3 (down from spec floor of 5; CIs documented)
  - judge: LLMJudge (opus-4-7), N=3 votes, rubric v1.1.0 (DECISIONS.md #13).

Outputs:
  - results/runs/chunk6_rigor.jsonl     append-only run records (idempotent)
  - results/runs/chunk6_rigor.db        SQLite mirror (Chunk 4 plumbing)
  - results/runs/chunk6_rigor_pareto.png   Pareto with task-level CIs
  - results/runs/chunk6_rigor_summary.md   leaderboard-shaped table

Use `--dry-run` to print the projected cell count and dollar cost without
spending; no model calls happen.
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import numpy as np

from tokenbench.core.env import load_env
from tokenbench.core.metrics import (
    accuracy,
    bootstrap_ci,
    per_record_tokens,
    summarize,
    tpca_curve,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.base import Dataset
from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.datasets.splits import load_manifest
from tokenbench.datasets.swe_qa import SweQaDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.judges.llm_judge import LLMJudge
from tokenbench.models.anthropic import AnthropicModel
from tokenbench.providers.graphify import GraphifyProvider
from tokenbench.providers.llmlingua import LLMLinguaProvider
from tokenbench.providers.rag import BM25RagProvider
from tokenbench.providers.raw_dump import RawDumpProvider
from tokenbench.providers.repo_map import RepoMapProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner, cells_count

# All providers, in canonical order.
PROVIDER_FACTORIES = [
    ("rag-bm25", BM25RagProvider),
    ("repo-map", RepoMapProvider),
    ("graphify", GraphifyProvider),
    ("llmlingua-rag", LLMLinguaProvider),
    ("raw-dump", RawDumpProvider),
]

# Providers excluded from SWE-QA per scope F: raw-dump alone is ~$300+
# on SWE-QA × sonnet-4-5 and is already Pareto-dominated in Chunk 3.
SWE_QA_EXCLUDED_PROVIDERS = {"raw-dump"}

# Per-pass per-model exclusions (scope F-trim, locked 2026-06-13). raw-dump
# on needle × sonnet-4-5 already hit acc=1.000 in Chunk 3 with no spread; a
# 5-repeat CI just confirms what we know. Keep raw-dump × gpt-4o-mini ×
# needle as a single-model datapoint for symmetry.
NEEDLE_EXCLUDED_PROVIDER_MODEL = {
    ("raw-dump", "bedrock.anthropic.claude-sonnet-4-5"),
}

MODELS = [
    "bedrock.anthropic.claude-sonnet-4-5",
    "openai.gpt-4o-mini",
]

# Pricing for the cost projection. Approximate $/M tokens via the
# enterprise gateway. Numbers updated 2026-06 from prior chunks' usage logs.
PRICE_IN = {
    "bedrock.anthropic.claude-sonnet-4-5": 3.00,
    "openai.gpt-4o-mini": 0.15,
    "bedrock.anthropic.claude-opus-4-7": 15.00,
}
PRICE_OUT = {
    "bedrock.anthropic.claude-sonnet-4-5": 15.00,
    "openai.gpt-4o-mini": 0.60,
    "bedrock.anthropic.claude-opus-4-7": 75.00,
}

# Per-cell input-token estimates from chunk3.jsonl medians (native).
# Used only for the dry-run projection.
EST_INPUT_TOKENS = {
    ("rag-bm25", "bedrock.anthropic.claude-sonnet-4-5"): 1305,
    ("rag-bm25", "openai.gpt-4o-mini"): 1087,
    ("graphify", "bedrock.anthropic.claude-sonnet-4-5"): 1854,
    ("graphify", "openai.gpt-4o-mini"): 1462,
    ("llmlingua-rag", "bedrock.anthropic.claude-sonnet-4-5"): 882,
    ("llmlingua-rag", "openai.gpt-4o-mini"): 604,
    ("repo-map", "bedrock.anthropic.claude-sonnet-4-5"): 9868,
    ("repo-map", "openai.gpt-4o-mini"): 8054,
    ("raw-dump", "bedrock.anthropic.claude-sonnet-4-5"): 99838,
    ("raw-dump", "openai.gpt-4o-mini"): 80088,
}

OUT_NEEDLE = 50      # bare function name + minimal padding
OUT_SWE_QA = 200     # 3-7 sentences

class _ManifestFilteredDataset(Dataset):
    """Wraps another Dataset and yields only tasks whose task_id is in `keep`.

    Used by the v1.0 close-out to run the rigor sweep against the held-out
    split without touching the underlying NeedleCodebaseDataset code path.
    """

    def __init__(self, inner: Dataset, keep: set[str]):
        self._inner = inner
        self._keep = keep
        self.name = f"{inner.name}-filtered"
        self.dataset_version = inner.dataset_version

    def tasks(self):
        for t in self._inner.tasks():
            if t.task_id in self._keep:
                yield t


JUDGE_MODEL = "bedrock.anthropic.claude-opus-4-7"
JUDGE_N_VOTES = 3
JUDGE_IN_PER_CALL = 1500   # rubric scaffold + question + reference + candidate
JUDGE_OUT_PER_CALL = 50    # JSON verdict


def _project_cost(
    needle_tasks: int,
    swe_qa_tasks: int,
    repeats: int,
    providers: list[str],
) -> tuple[float, float, dict]:
    answer_cost = 0.0
    breakdown: dict = {}
    for pname in providers:
        for mname in MODELS:
            in_tok = EST_INPUT_TOKENS[(pname, mname)]
            # needle pass — skip per-(provider,model) exclusions
            if (pname, mname) not in NEEDLE_EXCLUDED_PROVIDER_MODEL:
                cells = needle_tasks * repeats
                in_cost = cells * in_tok / 1e6 * PRICE_IN[mname]
                out_cost = cells * OUT_NEEDLE / 1e6 * PRICE_OUT[mname]
                sub = in_cost + out_cost
                breakdown[(pname, mname, "needle")] = (cells, sub)
                answer_cost += sub
            # swe-qa pass
            if pname in SWE_QA_EXCLUDED_PROVIDERS:
                continue
            cells = swe_qa_tasks * repeats
            in_cost = cells * in_tok / 1e6 * PRICE_IN[mname]
            out_cost = cells * OUT_SWE_QA / 1e6 * PRICE_OUT[mname]
            sub = in_cost + out_cost
            breakdown[(pname, mname, "swe_qa")] = (cells, sub)
            answer_cost += sub

    swe_providers = [p for p in providers if p not in SWE_QA_EXCLUDED_PROVIDERS]
    judge_cells = swe_qa_tasks * len(swe_providers) * len(MODELS) * repeats
    judge_calls = judge_cells * JUDGE_N_VOTES
    judge_cost = judge_calls * (
        JUDGE_IN_PER_CALL / 1e6 * PRICE_IN[JUDGE_MODEL]
        + JUDGE_OUT_PER_CALL / 1e6 * PRICE_OUT[JUDGE_MODEL]
    )
    return answer_cost, judge_cost, breakdown


def _print_projection(
    needle_tasks: int,
    swe_qa_tasks: int,
    repeats: int,
    providers: list[str],
) -> None:
    answer_cost, judge_cost, breakdown = _project_cost(
        needle_tasks, swe_qa_tasks, repeats, providers,
    )
    print(f"\n=== Cost projection (scope F frozen 2026-06-13) ===")
    print(f"needle tasks: {needle_tasks}  swe-qa tasks: {swe_qa_tasks}  repeats: {repeats}")
    print(f"providers (needle): {providers}")
    print(f"providers (swe-qa): {[p for p in providers if p not in SWE_QA_EXCLUDED_PROVIDERS]}")
    print()
    print(f"{'provider':14s} {'model':36s} {'pass':8s} {'cells':>6}  est $")
    total = 0.0
    for k in sorted(breakdown):
        cells, sub = breakdown[k]
        print(f"{k[0]:14s} {k[1]:36s} {k[2]:8s} {cells:>6}  ${sub:>6.2f}")
        total += sub
    print(f"{'':60s} {'answer subtotal':>15s}  ${answer_cost:>6.2f}")
    swe_providers = [p for p in providers if p not in SWE_QA_EXCLUDED_PROVIDERS]
    judge_cells = swe_qa_tasks * len(swe_providers) * len(MODELS) * repeats
    print(f"\njudge: {judge_cells:,} cells × {JUDGE_N_VOTES} votes "
          f"= {judge_cells * JUDGE_N_VOTES:,} {JUDGE_MODEL} calls  ${judge_cost:.2f}")
    print(f"\n=== TOTAL projected: ${answer_cost + judge_cost:.2f} ===")


def _summarize_records(
    records: list[RunRecord],
    *,
    label: str,
) -> list[dict]:
    by_pm: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for r in records:
        by_pm[(r.provider.name, r.model)].append(r)

    print(f"\n=== {label} summary ===")
    print(f"{'provider':14s} {'model':36s} {'n':>4} {'acc':>6} "
          f"{'TPCA(V=1)':>11} {'TPCA(V=100)':>12} {'TPCA(V=10k)':>12}  "
          f"{'med tok':>9}  acc 95% CI")
    rows = []
    for (pname, mname), recs in sorted(by_pm.items()):
        if not recs:
            continue
        acc = accuracy(recs)
        curve = tpca_curve(recs)
        per_v1 = per_record_tokens(recs, V=1)
        med = summarize(per_v1).median
        # task-level acc CI: bootstrap on the per-task mean correctness across repeats
        by_task: dict[str, list[float]] = defaultdict(list)
        for r in recs:
            by_task[r.task_id].append(1.0 if r.score.correct else 0.0)
        per_task = [float(np.mean(v)) for v in by_task.values()]
        ci_lo, ci_hi = bootstrap_ci(per_task, seed=0)
        print(f"{pname:14s} {mname:36s} {len(recs):>4} {acc:>6.3f} "
              f"{curve[1]:>11.0f} {curve[100]:>12.0f} {curve[10_000]:>12.0f}  "
              f"{med:>9.0f}  [{ci_lo:.3f}, {ci_hi:.3f}]")
        rows.append({
            "provider": pname, "model": mname, "n": len(recs), "n_tasks": len(by_task),
            "acc": acc, "ci_low": ci_lo, "ci_high": ci_hi,
            "tpca_v1": curve[1], "tpca_v100": curve[100], "tpca_v10000": curve[10_000],
            "median_tokens_v1": med, "label": label,
        })
    return rows


def _write_summary_md(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        fh.write("# Chunk 6 deliverable C — rigor sweep summary\n\n")
        fh.write("Task-level bootstrap 95% CI on accuracy "
                 "(per-task correctness averaged across repeats).\n\n")
        for label in sorted({r["label"] for r in rows}):
            fh.write(f"## {label}\n\n")
            fh.write("| provider | model | cells | tasks | acc | 95% CI | "
                     "TPCA(V=1) | TPCA(V=100) | TPCA(V=10k) | median tok |\n")
            fh.write("|---|---|---:|---:|---:|---|---:|---:|---:|---:|\n")
            for r in [x for x in rows if x["label"] == label]:
                fh.write(
                    f"| {r['provider']} | {r['model'].split('.')[-1]} "
                    f"| {r['n']} | {r['n_tasks']} | {r['acc']:.3f} "
                    f"| [{r['ci_low']:.3f}, {r['ci_high']:.3f}] "
                    f"| {r['tpca_v1']:,.0f} | {r['tpca_v100']:,.0f} "
                    f"| {r['tpca_v10000']:,.0f} | {r['median_tokens_v1']:,.0f} |\n"
                )
            fh.write("\n")
    print(f"Summary md → {out_path}")


def _plot_pareto_with_ci(records_all: list[RunRecord], out_path: Path,
                         V: int = 100) -> None:
    import matplotlib.pyplot as plt

    by_label: dict[str, list[RunRecord]] = defaultdict(list)
    for r in records_all:
        # crude split: needle vs swe-qa by task_id prefix
        label = "needle" if r.task_id.startswith("needle-") else "swe_qa"
        by_label[label].append(r)

    fig, axes = plt.subplots(1, len(by_label), figsize=(13, 5), sharey=True)
    if len(by_label) == 1:
        axes = [axes]
    markers = {MODELS[0]: "o", MODELS[1]: "s"}
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    color_for = {p: colors[i] for i, (p, _) in enumerate(PROVIDER_FACTORIES)}

    for ax, label in zip(axes, sorted(by_label)):
        by_pm: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
        for r in by_label[label]:
            by_pm[(r.provider.name, r.model)].append(r)
        for (pname, mname), recs in by_pm.items():
            per_task: dict[str, list[float]] = defaultdict(list)
            for r in recs:
                per_task[r.task_id].append(1.0 if r.score.correct else 0.0)
            per_task_acc = [float(np.mean(v)) for v in per_task.values()]
            ci_lo, ci_hi = bootstrap_ci(per_task_acc, seed=0)
            mean_tokens = float(np.mean(per_record_tokens(recs, V=V)))
            ax.errorbar(
                mean_tokens, accuracy(recs),
                yerr=[[accuracy(recs) - ci_lo], [ci_hi - accuracy(recs)]],
                fmt=markers.get(mname, "x"),
                color=color_for[pname], markersize=10,
                ecolor="grey", capsize=3, alpha=0.85,
                label=f"{pname} / {mname.split('.')[-1]}",
            )
        ax.set_xscale("log")
        ax.set_xlabel(f"mean tokens / cell at V={V} (log)")
        ax.set_title(f"{label} — accuracy vs tokens (V={V})")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, which="both", alpha=0.3)
    axes[0].set_ylabel("accuracy (with task-level 95% CI)")
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", bbox_to_anchor=(1.0, 0.5),
               fontsize=7, frameon=True)
    fig.suptitle("Chunk 6 rigor: task-level bootstrap CIs across repeats", y=1.0)
    fig.tight_layout(rect=(0, 0, 0.85, 0.97))
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    print(f"Plot → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print cost projection and exit without spending.")
    ap.add_argument("--needle-tasks-per-repo", type=int, default=8)
    ap.add_argument(
        "--needle-manifest", default=None,
        help="If set, restrict needle tasks to task_ids in this manifest. "
             "When used, --needle-tasks-per-repo is forced to 100 so the "
             "underlying dataset enumerates the full v1.0 task list "
             "before filtering.",
    )
    ap.add_argument("--swe-qa-sample",
                    default="artifacts/swe_qa/v1.0.0/sample_chunk6.jsonl")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out-dir", default="results/runs")
    ap.add_argument("--store-name", default="chunk6_rigor")
    ap.add_argument("--judge-run-id", default=None,
                    help="Sticky judge audit-log id; default auto-generated.")
    ap.add_argument(
        "--skip", choices=["none", "needle", "swe_qa"], default="none",
        help="Skip one pass; useful for resuming after a kill mid-sweep.",
    )
    args = ap.parse_args()

    if args.needle_manifest:
        keep = load_manifest(Path(args.needle_manifest))
        if not keep:
            raise SystemExit(f"empty/missing needle manifest: {args.needle_manifest}")
        # Force max-per-repo high enough to enumerate every v1.0 needle task
        # before the manifest filter trims it; the freeze script used 100.
        inner = NeedleCodebaseDataset(max_tasks_per_repo=100)
        needle_ds: Dataset = _ManifestFilteredDataset(inner, keep)
    else:
        needle_ds = NeedleCodebaseDataset(max_tasks_per_repo=args.needle_tasks_per_repo)
    n_needle = sum(1 for _ in needle_ds.tasks())
    swe_qa_path = Path(args.swe_qa_sample)
    swe_qa_ds = SweQaDataset(questions_path=swe_qa_path)
    n_swe = sum(1 for _ in swe_qa_ds.tasks())

    providers = [name for name, _ in PROVIDER_FACTORIES]

    _print_projection(n_needle, n_swe, args.repeats, providers)

    if args.dry_run:
        print("\n[dry-run] no model calls made.")
        return

    load_env()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = ResultsStore(out_dir / f"{args.store_name}.jsonl")
    runner = Runner(store)
    cfg = RunConfig(repeats=args.repeats, base_seed=1, concurrency=args.concurrency)

    judge_run_id = args.judge_run_id or f"chunk6-{uuid4().hex[:8]}"
    print(f"\nJudge run id: {judge_run_id}")

    answering_models = [AnthropicModel(m) for m in MODELS]

    # --- Pass 1: needle, AutoContainsJudge ---
    # Per-provider model filter to honor NEEDLE_EXCLUDED_PROVIDER_MODEL.
    if args.skip != "needle":
        total_cells = 0
        groups: list[tuple] = []
        for pname, cls in PROVIDER_FACTORIES:
            allowed_models = [
                m for m in answering_models
                if (pname, m.name) not in NEEDLE_EXCLUDED_PROVIDER_MODEL
            ]
            if not allowed_models:
                print(f"  (needle: skipping {pname} — all models excluded)")
                continue
            inst = cls()
            n_cells = cells_count(n_needle, 1, len(allowed_models), args.repeats)
            total_cells += n_cells
            groups.append((inst, allowed_models, n_cells))

        print(f"\n--- Needle pass: {total_cells} cells across "
              f"{len(groups)} provider group(s) (F-trim exclusions applied) ---")
        skipped: list = []
        for inst, allowed_models, n_cells in groups:
            model_short = [m.name.split('.')[-1] for m in allowed_models]
            print(f"  needle: {inst.name} × {model_short} × {args.repeats} repeats "
                  f"= {n_cells} cells")
            runner.sweep(
                dataset=needle_ds,
                providers=[inst],
                models=allowed_models,
                judge=AutoContainsJudge(),
                config=cfg,
                on_skip=skipped.append,
            )
        if skipped:
            print(f"  (idempotent skip: {len(skipped)} cell(s) already in store)")

    # --- Pass 2: SWE-QA, LLMJudge, providers minus raw-dump ---
    if args.skip != "swe_qa":
        swe_providers = [cls() for name, cls in PROVIDER_FACTORIES
                         if name not in SWE_QA_EXCLUDED_PROVIDERS]
        n_cells = cells_count(n_swe, len(swe_providers),
                              len(answering_models), args.repeats)
        print(f"\n--- SWE-QA pass: {n_cells} cells "
              f"({n_swe}t × {len(swe_providers)}p × {len(answering_models)}m × {args.repeats}r) ---")
        judge = LLMJudge(
            AnthropicModel(JUDGE_MODEL),
            n_votes=JUDGE_N_VOTES,
            judge_run_id=judge_run_id,
        )
        skipped = []
        runner.sweep(
            dataset=swe_qa_ds,
            providers=swe_providers,
            models=answering_models,
            judge=judge,
            config=cfg,
            on_skip=skipped.append,
        )
        if skipped:
            print(f"  (idempotent skip: {len(skipped)} cell(s) already in store)")

    # --- Summarize ---
    all_records = list(store.all())
    needle_recs = [r for r in all_records if r.task_id.startswith("needle-")]
    swe_recs = [r for r in all_records if r.task_id.startswith("swe-")]
    rows: list[dict] = []
    if needle_recs:
        rows.extend(_summarize_records(needle_recs, label="needle"))
    if swe_recs:
        rows.extend(_summarize_records(swe_recs, label="swe_qa"))
    _write_summary_md(rows, out_dir / f"{args.store_name}_summary.md")
    _plot_pareto_with_ci(all_records, out_dir / f"{args.store_name}_pareto.png", V=100)


if __name__ == "__main__":
    main()
