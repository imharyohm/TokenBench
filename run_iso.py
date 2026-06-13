"""Chunk 6 deliverable B — iso-accuracy / iso-budget reporting.

Reads existing run records (default: results/runs/chunk3.jsonl, the 5×2
sweep from Chunk 3), computes:

  - Iso-accuracy: tokens/query (at V ∈ {1, 100, 10000}) needed to reach
    acc ∈ {0.5, 0.7, 0.9}. None when a method never reached the target.
  - Iso-budget: accuracy a method reaches when per-query tokens (at V ∈
    {1, 100, 10000}) are constrained to budget ∈ {1k, 10k, 100k}.

Outputs:
  - printed markdown tables (per-V, per-target panels)
  - results/runs/chunk6_iso.png (small-multiples)

No new gateway calls — pure analytics over the Chunk 3 store.
Settings (handoff #3, #4): targets {50, 70, 90}%, budgets {1k, 10k, 100k}.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    accuracy,
    iso_accuracy_tokens,
    iso_budget_accuracy,
    per_record_tokens,
)
from tokenbench.results.store import ResultsStore


ISO_ACC_TARGETS = (0.5, 0.7, 0.9)
ISO_BUDGET_TARGETS = (1_000.0, 10_000.0, 100_000.0)


def _group_by_method(records, keep_models: set[str] | None = None
                     ) -> dict[tuple[str, str], list]:
    """Group by (provider_name, model). Returns dict of (provider, model) -> records."""
    by_pm: dict[tuple[str, str], list] = defaultdict(list)
    for r in records:
        if keep_models and r.model not in keep_models:
            continue
        by_pm[(r.provider.name, r.model)].append(r)
    return dict(by_pm)


def _print_iso_acc_table(records, V: int) -> None:
    by_pm = _group_by_method(records)
    rows = sorted(by_pm)
    print(f"\n## Iso-accuracy at V={V} — tokens/query needed to reach target acc")
    print()
    header = f"| {'method':24s} | {'model':36s} | "
    header += " | ".join(f"acc≥{int(t*100)}% (tokens)" for t in ISO_ACC_TARGETS)
    header += f" | acc reached |"
    print(header)
    print("|" + "|".join("-" * (len(c) + 2) for c in header.split("|")[1:-1]) + "|")
    for (pname, mname) in rows:
        recs = by_pm[(pname, mname)]
        cells: list[str] = []
        acc_reached: float = accuracy(recs)
        for target in ISO_ACC_TARGETS:
            pts = iso_accuracy_tokens({pname: recs}, target_acc=target, V=float(V))
            p = pts[0]
            if p.tokens is None:
                cells.append(f"— (peaked {p.acc_reached:.2f})")
            else:
                cells.append(f"{p.tokens:,.0f}")
        cell_str = " | ".join(c.rjust(20) for c in cells)
        short_model = mname.split(".")[-1]
        print(f"| {pname:24s} | {short_model:36s} | {cell_str} | {acc_reached:.3f} |")


def _print_iso_budget_table(records, V: int) -> None:
    by_pm = _group_by_method(records)
    rows = sorted(by_pm)
    print(f"\n## Iso-budget at V={V} — accuracy reached under per-query token budget")
    print()
    header = f"| {'method':24s} | {'model':36s} | "
    header += " | ".join(f"budget {int(b/1000)}k" for b in ISO_BUDGET_TARGETS)
    header += f" | tokens used |"
    print(header)
    print("|" + "|".join("-" * (len(c) + 2) for c in header.split("|")[1:-1]) + "|")
    for (pname, mname) in rows:
        recs = by_pm[(pname, mname)]
        cells: list[str] = []
        per = per_record_tokens(recs, V=float(V))
        mean_tokens = float(np.mean(per)) if per else 0.0
        for budget in ISO_BUDGET_TARGETS:
            pts = iso_budget_accuracy({pname: recs}, budget_tokens=budget, V=float(V))
            p = pts[0]
            if not p.feasible:
                cells.append(f"— (>{int(budget/1000)}k)")
            else:
                cells.append(f"{p.accuracy:.3f}")
        cell_str = " | ".join(c.rjust(14) for c in cells)
        short_model = mname.split(".")[-1]
        print(f"| {pname:24s} | {short_model:36s} | {cell_str} | {mean_tokens:,.0f} |")


def _plot_iso(records, out_path: Path) -> None:
    """3 columns (V=1/100/10k) × 2 rows (iso-accuracy / iso-budget).

    Iso-accuracy row: x=tokens-to-reach-target (log), y=target%, one curve
      per (method, model). Methods that don't reach a target are omitted
      from that x-axis position; their cell is empty (we mark this in the
      table, not the plot).
    Iso-budget row: x=budget (log), y=accuracy reached. Infeasible budgets
      get the leftmost open marker.
    """
    by_pm = _group_by_method(records)
    methods = sorted({pname for (pname, _) in by_pm})
    models = sorted({mname for (_, mname) in by_pm})

    color_for = {m: plt.cm.tab10(i / max(1, len(methods))) for i, m in enumerate(methods)}
    marker_for = {mname: ("o" if i == 0 else "x") for i, mname in enumerate(models)}

    fig, axes = plt.subplots(2, 3, figsize=(15.5, 8.0), sharey="row")
    Vs = list(DEFAULT_AMORTIZATION_VOLUMES)

    # Row 0: iso-accuracy
    for col, V in enumerate(Vs):
        ax = axes[0, col]
        for (pname, mname), recs in by_pm.items():
            xs, ys = [], []
            for target in ISO_ACC_TARGETS:
                pts = iso_accuracy_tokens({pname: recs}, target_acc=target, V=float(V))
                p = pts[0]
                if p.tokens is not None:
                    xs.append(p.tokens)
                    ys.append(target)
            if xs:
                ax.plot(xs, ys, "-",
                        color=color_for[pname], alpha=0.7, linewidth=1.5)
                kw = dict(marker=marker_for[mname], color=color_for[pname], s=70,
                          label=f"{pname} / {mname.split('.')[-1]}")
                if marker_for[mname] != "x":
                    kw.update(edgecolors="black", linewidths=0.5)
                ax.scatter(xs, ys, **kw)
        ax.set_xscale("log")
        ax.set_xlabel(f"tokens/query (V={V}, log)")
        ax.set_ylim(0.4, 1.0)
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(f"Iso-accuracy (V={V})")
        for t in ISO_ACC_TARGETS:
            ax.axhline(t, color="grey", linestyle=":", alpha=0.3)
    axes[0, 0].set_ylabel("target accuracy")

    # Row 1: iso-budget
    for col, V in enumerate(Vs):
        ax = axes[1, col]
        for (pname, mname), recs in by_pm.items():
            xs, ys = [], []
            for budget in ISO_BUDGET_TARGETS:
                pts = iso_budget_accuracy({pname: recs}, budget_tokens=budget, V=float(V))
                p = pts[0]
                if p.feasible:
                    xs.append(budget)
                    ys.append(p.accuracy)
            if xs:
                ax.plot(xs, ys, "-",
                        color=color_for[pname], alpha=0.7, linewidth=1.5)
                kw = dict(marker=marker_for[mname], color=color_for[pname], s=70,
                          label=f"{pname} / {mname.split('.')[-1]}")
                if marker_for[mname] != "x":
                    kw.update(edgecolors="black", linewidths=0.5)
                ax.scatter(xs, ys, **kw)
        ax.set_xscale("log")
        ax.set_xlabel(f"budget tokens/query (V={V}, log)")
        ax.set_ylim(0, 1.05)
        ax.grid(True, which="both", alpha=0.3)
        ax.set_title(f"Iso-budget (V={V})")
        for b in ISO_BUDGET_TARGETS:
            ax.axvline(b, color="grey", linestyle=":", alpha=0.3)
    axes[1, 0].set_ylabel("accuracy reached")

    # Single legend at the right
    handles, labels = axes[0, -1].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="center right",
                   bbox_to_anchor=(1.0, 0.5), fontsize=7, frameon=True)
    fig.suptitle("Chunk 6 deliverable B — Iso-accuracy / iso-budget across V",
                 fontsize=13, y=1.0)
    fig.tight_layout(rect=(0, 0, 0.88, 0.97))
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    print(f"\nPlot → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default="results/runs/chunk3.jsonl",
                    help="Path to a JSONL run-records store.")
    ap.add_argument("--out-dir", default="results/runs")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Optional subset of model names; default = all in store.")
    args = ap.parse_args()

    store = ResultsStore(Path(args.records))
    records = list(store.all())
    if args.models:
        keep = set(args.models)
        records = [r for r in records if r.model in keep]
    if not records:
        raise SystemExit(f"No records loaded from {args.records}.")
    print(f"Loaded {len(records)} records from {args.records}")
    models = sorted({r.model for r in records})
    providers = sorted({r.provider.name for r in records})
    print(f"  Providers: {providers}")
    print(f"  Models:    {models}")

    for V in DEFAULT_AMORTIZATION_VOLUMES:
        _print_iso_acc_table(records, V=V)
    for V in DEFAULT_AMORTIZATION_VOLUMES:
        _print_iso_budget_table(records, V=V)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _plot_iso(records, out_dir / "chunk6_iso.png")


if __name__ == "__main__":
    main()
