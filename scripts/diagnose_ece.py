"""Diagnose ECE drivers from an existing calibration report — no new spend.

Reads results/judge/calibration_<run>.json and the matching audit log
results/judge/<run>.jsonl, then breaks ECE down to find what's actually
driving the failure.

Outputs (stdout):
  1. Per-bin ECE breakdown — which bin contributes the most error
  2. Confusion matrix (human pass/fail × judge pass/fail)
  3. Per-dimension distributions of judge scores (which dim is too strict?)
  4. Effect of relaxing the pass floor — counterfactual without re-running judge

CLI:
    python scripts/diagnose_ece.py results/judge/calibration_judge-5f2c4466.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_calibration(path: Path) -> dict:
    return json.loads(path.read_text())


def load_audit_log(path: Path) -> dict[str, list[dict]]:
    """Map task_id → list of N vote records."""
    out: dict[str, list[dict]] = {}
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out[rec["task_id"]] = rec["votes"]
    return out


def per_bin_ece(per_task: list[dict], n_bins: int = 10) -> list[dict]:
    """Re-derive ECE bin-by-bin so we can see contributions."""
    edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[dict] = []
    n = len(per_task)
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        in_bin = [
            t for t in per_task
            if (t["confidence"] >= lo and (t["confidence"] < hi or
                (i == n_bins - 1 and t["confidence"] <= hi)))
        ]
        if not in_bin:
            bins.append({"range": (lo, hi), "n": 0, "mean_conf": None,
                         "empirical_pass": None, "gap": 0.0, "contrib": 0.0})
            continue
        mean_conf = sum(t["confidence"] for t in in_bin) / len(in_bin)
        empirical = sum(1 for t in in_bin if t["human"]) / len(in_bin)
        gap = abs(mean_conf - empirical)
        contrib = (len(in_bin) / n) * gap
        bins.append({
            "range": (lo, hi),
            "n": len(in_bin),
            "mean_conf": mean_conf,
            "empirical_pass": empirical,
            "gap": gap,
            "contrib": contrib,
        })
    return bins


def confusion(per_task: list[dict]) -> dict:
    cm = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for t in per_task:
        h, j = t["human"], t["judge"]
        if h and j:
            cm["tp"] += 1
        elif j and not h:
            cm["fp"] += 1
        elif not j and not h:
            cm["tn"] += 1
        elif h and not j:
            cm["fn"] += 1
    return cm


def per_dim_stats(audit_by_task: dict[str, list[dict]],
                  per_task: list[dict]) -> dict:
    """For each rubric dim, distribution of vote scores split by human label."""
    dims = ("correctness", "completeness", "faithfulness")
    out: dict[str, dict] = {}
    for dim in dims:
        when_h_pass: list[int] = []
        when_h_fail: list[int] = []
        for t in per_task:
            tid = t["task_id"]
            if tid not in audit_by_task:
                continue
            for v in audit_by_task[tid]:
                if "_parse_error" in v["dims"]:
                    continue
                score = v["dims"][dim]
                if t["human"]:
                    when_h_pass.append(score)
                else:
                    when_h_fail.append(score)
        out[dim] = {
            "when_human_pass": dict(Counter(when_h_pass)),
            "when_human_fail": dict(Counter(when_h_fail)),
            "mean_when_h_pass": (sum(when_h_pass) / len(when_h_pass)
                                 if when_h_pass else None),
            "mean_when_h_fail": (sum(when_h_fail) / len(when_h_fail)
                                 if when_h_fail else None),
        }
    return out


def counterfactual_floor(audit_by_task: dict[str, list[dict]],
                         per_task: list[dict],
                         floors: dict[str, int]) -> dict:
    """What would κ and ECE be if PASS_FLOOR were `floors`?

    Re-derive each task's pass/fail and confidence from the saved vote dims,
    using the new floor. No new judge calls.
    """
    judge_pass: list[bool] = []
    judge_conf: list[float] = []
    human_pass: list[bool] = []
    for t in per_task:
        tid = t["task_id"]
        if tid not in audit_by_task:
            continue
        votes = audit_by_task[tid]
        passes = []
        for v in votes:
            d = v["dims"]
            if "_parse_error" in d:
                passes.append(False)
                continue
            ok = all(d.get(k, 0) >= floor for k, floor in floors.items())
            passes.append(ok)
        n = len(passes)
        if n == 0:
            continue
        pass_count = sum(passes)
        majority_pass = pass_count > n // 2
        confidence = pass_count / n
        judge_pass.append(majority_pass)
        judge_conf.append(confidence)
        human_pass.append(t["human"])

    # κ
    n = len(judge_pass)
    if n == 0:
        return {"kappa": 0.0, "ece": 0.0, "n": 0,
                "n_pass_judge": 0, "raw_agreement": 0.0}
    p_o = sum(1 for x, y in zip(judge_pass, human_pass) if x == y) / n
    pa = sum(judge_pass) / n
    pb = sum(human_pass) / n
    p_e = pa * pb + (1 - pa) * (1 - pb)
    kappa = 0.0 if abs(1 - p_e) < 1e-12 else (p_o - p_e) / (1 - p_e)

    # ECE (10 bins)
    edges = [i / 10 for i in range(11)]
    ece = 0.0
    for i in range(10):
        lo, hi = edges[i], edges[i + 1]
        idxs = [j for j, c in enumerate(judge_conf)
                if (c >= lo and (c < hi or (i == 9 and c <= hi)))]
        if not idxs:
            continue
        bin_conf = sum(judge_conf[j] for j in idxs) / len(idxs)
        bin_acc = sum(1 for j in idxs if human_pass[j]) / len(idxs)
        ece += (len(idxs) / n) * abs(bin_conf - bin_acc)

    return {
        "kappa": kappa,
        "ece": ece,
        "n": n,
        "n_pass_judge": sum(judge_pass),
        "n_pass_human": sum(human_pass),
        "raw_agreement": p_o,
    }


def fmt_pct(x: float) -> str:
    return f"{x*100:5.1f}%"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("calibration_json", type=Path,
                   help="results/judge/calibration_*.json")
    p.add_argument("--audit-log", type=Path, default=None,
                   help="audit JSONL (default: derived from calibration_json filename)")
    args = p.parse_args()

    cal = load_calibration(args.calibration_json)
    audit_path = args.audit_log or (
        args.calibration_json.parent /
        f"{cal['judge_run_id']}.jsonl"
    )
    audit_by_task = load_audit_log(audit_path) if audit_path.exists() else {}

    per_task = cal["per_task"]
    n = len(per_task)

    print("=" * 72)
    print(f"ECE diagnostics — {cal['judge_run_id']}")
    print("=" * 72)
    print(f"  judge_model     : {cal['judge_model']}")
    print(f"  n_votes         : {cal['n_votes']}")
    print(f"  n_evaluated     : {n}")
    print(f"  reported κ      : {cal['cohens_kappa']:+.3f}  "
          f"(threshold ≥ {cal['thresholds']['kappa_pass']})")
    print(f"  reported ECE    : {cal['ece']:.4f}  "
          f"(threshold ≤ {cal['thresholds']['ece_pass']})")
    print()

    # 1. Per-bin ECE breakdown
    print("─" * 72)
    print("1. PER-BIN ECE BREAKDOWN")
    print("─" * 72)
    print(f"  {'bin':<14} {'n':>4} {'mean_conf':>10} {'h_pass_rate':>12} "
          f"{'gap':>7} {'contrib':>9}")
    bins = per_bin_ece(per_task)
    for b in bins:
        lo, hi = b["range"]
        if b["n"] == 0:
            continue
        print(f"  [{lo:.2f}, {hi:.2f}) {b['n']:>4} "
              f"{b['mean_conf']:>10.3f} {fmt_pct(b['empirical_pass']):>12} "
              f"{b['gap']:>7.3f} {b['contrib']:>9.4f}")
    print(f"  {'TOTAL':<14} {n:>4} {' ':>10} {' ':>12} "
          f"{' ':>7} {sum(b['contrib'] for b in bins):>9.4f}")
    print()
    print("  ECE drivers: bins with high contrib are where confidence")
    print("  diverges most from human ground truth.")
    print()

    # 2. Confusion
    print("─" * 72)
    print("2. CONFUSION MATRIX (human × judge)")
    print("─" * 72)
    cm = confusion(per_task)
    print(f"                     judge=PASS    judge=FAIL")
    print(f"   human=PASS         {cm['tp']:>4}          {cm['fn']:>4}")
    print(f"   human=FAIL         {cm['fp']:>4}          {cm['tn']:>4}")
    print()
    fn_rate = cm['fn'] / (cm['tp'] + cm['fn']) if (cm['tp'] + cm['fn']) else 0
    fp_rate = cm['fp'] / (cm['fp'] + cm['tn']) if (cm['fp'] + cm['tn']) else 0
    print(f"  False-NEG rate (judge says fail, human says pass): {fn_rate:.3f}  "
          f"← under-passing")
    print(f"  False-POS rate (judge says pass, human says fail): {fp_rate:.3f}  "
          f"← over-passing")
    print()

    if not audit_by_task:
        print(f"⚠  audit log not found at {audit_path} — skipping per-dim and")
        print(f"   counterfactual sections (need raw vote dims).")
        return

    # 3. Per-dimension distributions
    print("─" * 72)
    print("3. PER-DIMENSION VOTE DISTRIBUTIONS")
    print("─" * 72)
    dims_stats = per_dim_stats(audit_by_task, per_task)
    for dim, s in dims_stats.items():
        print(f"\n  {dim}:")
        print(f"    when human=PASS: {s['when_human_pass']}  "
              f"(mean={s['mean_when_h_pass']:.2f})")
        print(f"    when human=FAIL: {s['when_human_fail']}  "
              f"(mean={s['mean_when_h_fail']:.2f})")
    print()
    print("  Look for: a dim where 'mean_when_h_pass' is much lower than 2,")
    print("  but the floor for that dim is high. That dim's threshold is")
    print("  the ECE driver — relaxing it converts FN→TP without changing")
    print("  TP→FP much.")
    print()

    # 4. Counterfactuals
    print("─" * 72)
    print("4. COUNTERFACTUALS — what if PASS_FLOOR changed?")
    print("─" * 72)
    print("  Re-deriving κ and ECE from saved vote dims, no new judge calls.")
    print()
    print(f"  {'floor (corr/comp/faith)':<28} {'κ':>7} {'ECE':>7}  "
          f"{'judge_pass':>10}  {'agree':>6}")
    floor_options = [
        {"correctness": 1, "completeness": 1, "faithfulness": 2},  # current
        {"correctness": 1, "completeness": 1, "faithfulness": 1},
        {"correctness": 1, "completeness": 0, "faithfulness": 2},
        {"correctness": 1, "completeness": 0, "faithfulness": 1},
        {"correctness": 2, "completeness": 1, "faithfulness": 2},
        {"correctness": 1, "completeness": 1, "faithfulness": 0},
        # any-dim-positive (pass if any dim ≥ 1)
        # we'll skip this — it's not a "floor" in the same sense
    ]
    for f in floor_options:
        cf = counterfactual_floor(audit_by_task, per_task, f)
        if cf["n"] == 0:
            continue
        floor_str = f"{f['correctness']}/{f['completeness']}/{f['faithfulness']}"
        marker = "  ← current" if f == floor_options[0] else ""
        print(f"  {floor_str:<28} {cf['kappa']:>+7.3f} {cf['ece']:>7.4f}  "
              f"{cf['n_pass_judge']:>10}  {cf['raw_agreement']:>6.3f}{marker}")
    print()
    print("  Read: a row where κ stays ≥ 0.6 AND ECE drops ≤ 0.10 = the")
    print("  rubric floor that would have passed calibration. If no row")
    print("  satisfies both, the issue isn't the floor — it's the rubric")
    print("  itself, the model, or the N=3 confidence granularity.")
    print()


if __name__ == "__main__":
    main()
