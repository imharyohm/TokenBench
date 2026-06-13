"""Chunk 6 deliverable A — trivial-baselines smoke test.

Runs ZeroContextProvider and ExploitBaselineProvider over the needle-codebase
dataset against sonnet-4-5 only (cheapest path). Two outputs:

  1. results/runs/chunk6_baselines.jsonl  — append-only run records
  2. printed table:

     provider           model         n   acc   med tok/cell
     zero-context       sonnet-4-5    12  X.XX     ~50
     exploit-baseline   sonnet-4-5    12  ~0.0     ~150

What this proves:
  - zero-context is the priors-only floor. Real providers should land
    strictly above this on the Pareto plot. If any real provider is
    BELOW zero-context on accuracy, that provider is adding noise.
  - exploit-baseline tries to game the harness via output tricks
    (candidate dump, judge-injection, lexical overlap). Should score ~0
    if defenses work — Chunk 6 exit gate 2.

Cost: ~$0.20 (24 cells, all very small inputs).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tokenbench.core.env import load_env
from tokenbench.core.metrics import (
    accuracy,
    paired_uplift_ci,
    per_record_tokens,
    summarize,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.needle_codebase import NeedleCodebaseDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.anthropic import AnthropicModel
from tokenbench.providers.exploit_baseline import ExploitBaselineProvider
from tokenbench.providers.zero_context import ZeroContextProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner, cells_count


PROVIDER_FACTORIES = [
    ("zero-context", ZeroContextProvider),
    ("exploit-baseline", ExploitBaselineProvider),
]

DEFAULT_MODEL = "bedrock.anthropic.claude-sonnet-4-5"


# Chunk 6 exit gate 2 — paired uplift threshold.
#
# The original gate ("exploit ~ 0") was wrong: it forgot the priors floor.
# Frontier models on public Python repos answer non-trivially many needle
# questions from training-time priors alone (zero-context is well above 0).
# What we actually want to verify is that the exploit's OUTPUT-side tactics
# (candidate dump, judge injection, lexical overlap) do not lift accuracy
# meaningfully above that priors floor, given a paired bootstrap CI.
#
# Tolerance T = 0.20 absolute paired uplift. PASS if ci_high <= T.
# Below T we treat any uplift as expected priors+candidate-priming noise on
# this dataset; above T it would indicate the harness or scorer is leaky.
# See research/exit_gate_2_priors_floor.md for the diagnosis and rationale.
EXIT_GATE_TOLERANCE = 0.20


def _summarize(records: list[RunRecord]) -> bool:
    by_pm: dict[tuple[str, str], list[RunRecord]] = {}
    for r in records:
        by_pm.setdefault((r.provider.name, r.model), []).append(r)

    print("\n=== Chunk 6 deliverable A — baseline summary ===")
    print(f"{'provider':18s} {'model':36s} {'n':>3} {'acc':>6}  {'med tok/cell':>12}")
    for (pname, mname), recs in sorted(by_pm.items()):
        acc = accuracy(recs)
        per_v1 = per_record_tokens(recs, V=1)
        med = summarize(per_v1).median
        print(f"{pname:18s} {mname:36s} {len(recs):>3} {acc:>6.3f}  {med:>12.0f}")
    print()
    print("Interpretation:")
    print("  - zero-context: the priors-only floor. Real providers must beat this.")
    print("  - exploit-baseline: rule-respecting output gaming. Verified below.")

    # Per-model paired uplift over zero-context.
    print("\n=== Exit gate 2 — paired uplift (exploit − zero-context) ===")
    models = sorted({r.model for r in records})
    all_pass = True
    for m in models:
        a = [r for r in records if r.model == m and r.provider.name == "exploit-baseline"]
        b = [r for r in records if r.model == m and r.provider.name == "zero-context"]
        if not a or not b:
            continue
        u = paired_uplift_ci(a, b, seed=0)
        verdict = "PASS" if u.ci_high <= EXIT_GATE_TOLERANCE else "FAIL"
        all_pass = all_pass and (verdict == "PASS")
        print(
            f"  {m:36s}  n={u.n:3d}  Δacc={u.mean:+.3f}  "
            f"95% CI [{u.ci_low:+.3f}, {u.ci_high:+.3f}]  "
            f"wins/ties/losses {u.wins}/{u.ties}/{u.losses}  "
            f"vs T={EXIT_GATE_TOLERANCE:+.2f} → {verdict}"
        )
    print(
        f"\n  Exit gate 2 verdict (Δacc CI upper ≤ {EXIT_GATE_TOLERANCE:+.2f}): "
        f"{'PASS' if all_pass else 'FAIL'}"
    )
    return all_pass


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-per-repo", type=int, default=4)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--out-dir", default="results/runs")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--providers", nargs="*", default=None,
        help="Subset of {zero-context, exploit-baseline}; default = both.",
    )
    args = ap.parse_args()

    providers = [
        cls() for name, cls in PROVIDER_FACTORIES
        if args.providers is None or name in args.providers
    ]
    models = [AnthropicModel(args.model)]

    dataset = NeedleCodebaseDataset(max_tasks_per_repo=args.tasks_per_repo)
    n_tasks = sum(1 for _ in dataset.tasks())
    cells = cells_count(n_tasks, len(providers), len(models), args.repeats)
    print(f"Baseline plan: {n_tasks} tasks × {len(providers)} providers "
          f"× 1 model × {args.repeats} repeats = {cells} cells")
    print(f"Providers: {[p.name for p in providers]}")
    print(f"Model: {args.model}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = ResultsStore(out_dir / "chunk6_baselines.jsonl")
    runner = Runner(store)

    skipped: list = []
    runner.sweep(
        dataset=dataset,
        providers=providers,
        models=models,
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=args.repeats, base_seed=1),
        on_skip=skipped.append,
    )
    if skipped:
        print(f"  (idempotent skip: {len(skipped)} cell(s) already in store)")

    selected_providers = {p.name for p in providers}
    selected_models = {m.name for m in models}
    records = [
        r for r in store.all()
        if r.provider.name in selected_providers
        and r.model in selected_models
        and r.dataset_version == dataset.dataset_version
        and r.repeat < args.repeats
    ]
    passed = _summarize(records)
    if not passed:
        print(
            "\n  NOTE: exit gate 2 is INCONCLUSIVE / FAIL on this sample. "
            "Either the CI is too wide (rerun with --tasks-per-repo 30+) "
            "or the exploit's priors+priming uplift truly exceeds T="
            f"{EXIT_GATE_TOLERANCE:+.2f}. See research/exit_gate_2_priors_floor.md."
        )


if __name__ == "__main__":
    main()
