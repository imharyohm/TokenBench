"""Regenerate the local leaderboard from a run-records store.

Per Chunk 6 deliverable H + spec exit gate 6: the leaderboard shows the
**accuracy-vs-normalized-token Pareto frontier** across methods, not a
single "Nx" claim.

Two cost columns are required (spec §7): `TPCA(V=1)` (cold start) and
`TPCA(V=10000)` (amortized). Median tokens/cell at V=1 is added as a
heavy-tail-aware sanity column. Task-level bootstrap 95% CIs on accuracy
come from `core.metrics.bootstrap_ci`.

The leaderboard is filtered to the **public split** by default
(DECISIONS.md #2). Held-out comparisons must be run separately with
`--include-heldout`; the resulting public-vs-heldout gap appears at the
bottom of the report.

Outputs:
  - LEADERBOARD.md       canonical, tracked in git
  - results/runs/leaderboard_<store-name>.md   per-store snapshot

No GitHub push at v1.0 (locked setting #6 in CONTEXT_HANDOFF.md).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    accuracy,
    bootstrap_ci,
    pareto_frontier,
    per_record_tokens,
    summarize,
    tpca_curve,
    ParetoPoint,
)
from tokenbench.core.schemas import RunRecord
from tokenbench.datasets.splits import load_manifest
from tokenbench.results.store import ResultsStore

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

PUBLIC_MANIFESTS = {
    "needle": _PROJECT_ROOT / "artifacts" / "needle" / "v1.0.0" / "public_split.tsv",
    "swe_qa": _PROJECT_ROOT / "artifacts" / "swe_qa" / "v1.0.0" / "public_split.tsv",
}
HELDOUT_MANIFESTS = {
    "needle": _PROJECT_ROOT / "artifacts" / "_heldout" / "needle" / "v1.0.0" / "heldout_split.tsv",
    "swe_qa": _PROJECT_ROOT / "artifacts" / "_heldout" / "swe_qa" / "v1.0.0" / "heldout_split.tsv",
}


def _label_for(record: RunRecord) -> str:
    return "needle" if record.task_id.startswith("needle-") else "swe_qa"


def _filter_records(
    records: list[RunRecord],
    *,
    include_heldout: bool,
) -> dict[str, dict[str, list[RunRecord]]]:
    """Group records into {label: {split: [records]}} after manifest filter."""
    out: dict[str, dict[str, list[RunRecord]]] = {
        "needle": {"public": [], "heldout": []},
        "swe_qa": {"public": [], "heldout": []},
    }
    pub_ids = {k: load_manifest(p) for k, p in PUBLIC_MANIFESTS.items()}
    held_ids = {k: load_manifest(p) for k, p in HELDOUT_MANIFESTS.items()}
    for r in records:
        label = _label_for(r)
        if r.task_id in pub_ids[label]:
            out[label]["public"].append(r)
        elif r.task_id in held_ids[label]:
            if include_heldout:
                out[label]["heldout"].append(r)
        # tasks not in either manifest (e.g. legacy chunk2/chunk3 records
        # with task_ids outside the frozen split) are dropped — the
        # leaderboard intentionally only ranks frozen-split entries.
    return out


def _summarize_cell(records: list[RunRecord]) -> dict | None:
    if not records:
        return None
    by_task: dict[str, list[float]] = defaultdict(list)
    for r in records:
        by_task[r.task_id].append(1.0 if r.score.correct else 0.0)
    per_task_acc = [float(np.mean(v)) for v in by_task.values()]
    ci_lo, ci_hi = bootstrap_ci(per_task_acc, seed=0)
    curve = tpca_curve(records)
    per_v1 = per_record_tokens(records, V=1)
    return {
        "n_cells": len(records),
        "n_tasks": len(by_task),
        "acc": accuracy(records),
        "ci_low": ci_lo,
        "ci_high": ci_hi,
        "tpca_v1": curve[1],
        "tpca_v10000": curve[10_000],
        "median_tokens_v1": summarize(per_v1).median,
    }


def _format_pareto_marker(method: str, pareto_methods: set[str]) -> str:
    return "★" if method in pareto_methods else " "


def _render_table(
    cells: dict[tuple[str, str], dict],
    label: str,
    split: str,
) -> str:
    """One markdown table for a (dataset, split) pair."""
    if not cells:
        return f"\n_No records for {label}/{split} on the frozen split._\n"
    # Pareto on accuracy vs mean tokens at V=1 (cold start).
    pareto = pareto_frontier([
        ParetoPoint(method=f"{p}/{m}", accuracy=c["acc"],
                    tokens_per_query=c["tpca_v1"])
        for (p, m), c in cells.items() if c["acc"] > 0
    ])
    pareto_methods = {p.method for p in pareto}

    lines = [
        f"### {label} ({split})",
        "",
        "| ★ | provider | model | n cells | n tasks | acc | 95% CI "
        "| TPCA(V=1) | TPCA(V=10000) | median tok |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    rows = sorted(cells.items(), key=lambda kv: -kv[1]["acc"])
    for (pname, mname), c in rows:
        method_key = f"{pname}/{mname}"
        marker = _format_pareto_marker(method_key, pareto_methods)
        short_model = mname.split(".")[-1]
        lines.append(
            f"| {marker} | {pname} | {short_model} | {c['n_cells']} | {c['n_tasks']} "
            f"| {c['acc']:.3f} | [{c['ci_low']:.3f}, {c['ci_high']:.3f}] "
            f"| {c['tpca_v1']:,.0f} | {c['tpca_v10000']:,.0f} | {c['median_tokens_v1']:,.0f} |"
        )
    lines.append("")
    lines.append(f"_★ marks the Pareto frontier (accuracy vs tokens at V=1)._")
    lines.append("")
    return "\n".join(lines)


def _render_gap_section(
    by_label_split: dict[str, dict[str, list[RunRecord]]],
) -> str:
    """Public-vs-heldout gap diagnostic, when both splits have records."""
    parts: list[str] = []
    for label in ("needle", "swe_qa"):
        pub_recs = by_label_split[label].get("public", [])
        held_recs = by_label_split[label].get("heldout", [])
        if not pub_recs or not held_recs:
            continue
        parts.append(f"\n### {label} — public vs held-out gap")
        parts.append("")
        parts.append("| provider | model | acc(public) | acc(heldout) | Δacc | flag |")
        parts.append("|---|---|---:|---:|---:|:---:|")
        # Group by (provider, model) within each split
        cells_pub = _cells(pub_recs)
        cells_held = _cells(held_recs)
        for k in sorted(set(cells_pub) | set(cells_held)):
            p, m = k
            a_pub = accuracy(cells_pub.get(k, []))
            a_held = accuracy(cells_held.get(k, []))
            gap = a_pub - a_held
            # DECISIONS.md #7 trigger: gap > 2× bootstrap CI on public.
            ci_lo, ci_hi = bootstrap_ci(
                [1.0 if r.score.correct else 0.0 for r in cells_pub.get(k, [])],
                seed=0,
            ) if cells_pub.get(k) else (0.0, 0.0)
            ci_width = ci_hi - ci_lo
            flag = "⚠️" if abs(gap) > 2 * ci_width and ci_width > 0 else " "
            parts.append(
                f"| {p} | {m.split('.')[-1]} | {a_pub:.3f} | {a_held:.3f} "
                f"| {gap:+.3f} | {flag} |"
            )
        parts.append("")
        parts.append(
            "_⚠️ marks |Δacc| > 2× bootstrap CI on public — "
            "potential contamination per DECISIONS.md #7._"
        )
        parts.append("")
    return "\n".join(parts) if parts else ""


def _cells(records: list[RunRecord]) -> dict[tuple[str, str], list[RunRecord]]:
    out: dict[tuple[str, str], list[RunRecord]] = defaultdict(list)
    for r in records:
        out[(r.provider.name, r.model)].append(r)
    return dict(out)


def render_leaderboard(
    records: list[RunRecord],
    *,
    include_heldout: bool,
    title: str = "TokenBench v1.0.0 leaderboard",
) -> str:
    by_label_split = _filter_records(records, include_heldout=include_heldout)

    parts: list[str] = [
        f"# {title}",
        "",
        "Generated from the local run-records store. Every cell is filtered "
        "to the **public split** (DECISIONS.md #2). The held-out split is "
        "private and never published.",
        "",
        "**Two cost columns** are required by Chunk 6 spec §7: TPCA(V=1) for "
        "cold-start cost, TPCA(V=10000) for amortized cost. The right answer "
        "depends on your query volume.",
        "",
        "**No single-number claim.** A method's place on this table is one "
        "(accuracy, tokens) point; the curve across V is what tells you which "
        "method fits which regime.",
        "",
        f"`dataset_version: 1.0.0` · `harness_version: 0.1.0` · "
        f"`JUDGE_RUBRIC_VERSION: 1.1.0`",
        "",
        "## Public-split rankings",
    ]

    # Per-dataset tables.
    for label in ("needle", "swe_qa"):
        recs = by_label_split[label]["public"]
        if not recs:
            continue
        cells = {k: s for k, v in _cells(recs).items()
                 if (s := _summarize_cell(v))}
        parts.append(_render_table(cells, label, "public"))

    if include_heldout:
        parts.append("\n## Held-out diagnostic")
        parts.append("")
        parts.append(
            "_Held-out numbers are NEVER published in releases. This section "
            "exists locally for the maintainer's contamination audit per "
            "DECISIONS.md #7._"
        )
        gap = _render_gap_section(by_label_split)
        if gap:
            parts.append(gap)

    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--records", default="results/runs/chunk6_rigor.jsonl",
        help="JSONL run-records store to summarize.",
    )
    ap.add_argument("--out", default="LEADERBOARD.md")
    ap.add_argument(
        "--include-heldout", action="store_true",
        help="Include held-out diagnostic (local audit only — never publish).",
    )
    args = ap.parse_args()

    store = ResultsStore(Path(args.records))
    records = list(store.all())
    print(f"Loaded {len(records)} records from {args.records}")

    md = render_leaderboard(records, include_heldout=args.include_heldout)
    Path(args.out).write_text(md)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
