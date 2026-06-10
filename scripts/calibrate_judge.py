"""Calibrate the LLM judge against the human gold set.

Inputs (all under artifacts/swe_qa/v<dataset_version>/):
    questions.jsonl     — SWE-QA tasks (Chunk 5 deliverable 1)
    candidates.jsonl    — model outputs to be judged. One row per task_id:
                          {"task_id": ..., "candidate": ..., "source": ...}
                          (source describes the (provider, model) used, for audit)
    human_labels.jsonl  — human pass/fail labels. One row per task_id:
                          {"task_id": ..., "label": "pass"|"fail",
                           "annotator_id": ..., "timestamp": ISO-8601,
                           "rationale": (optional)}

The script runs the LLM judge on each (task, candidate) pair, then compares
its binary verdict to the human label.

Pass criteria (DECISIONS.md #11, #12, Chunk 5 exit gates 1-2):
    Cohen's κ ≥ 0.6   — primary calibration threshold
    ECE       ≤ 0.10  — primary; ≤ 0.05 earns "well-calibrated" badge

Output:
    results/judge/calibration_<judge_run_id>.json — full report
    Stdout — human-readable summary

CLI:
    python scripts/calibrate_judge.py \
        --version 1.0.0 \
        --judge-model bedrock.anthropic.claude-opus-4-7 \
        --n-votes 3
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tokenbench.datasets.swe_qa import QUESTIONS_DIR, SweQaDataset  # noqa: E402
from tokenbench.judges.llm_judge import (  # noqa: E402
    DEFAULT_JUDGE_MODEL,
    DEFAULT_N_VOTES,
    LLMJudge,
)
from tokenbench.models.anthropic import AnthropicModel  # noqa: E402

REPORT_DIR = PROJECT_ROOT / "results" / "judge"
KAPPA_PASS = 0.60
ECE_PASS = 0.10
ECE_BADGE = 0.05


@dataclass
class HumanLabel:
    task_id: str
    label: bool  # True=pass, False=fail
    annotator_id: str
    timestamp: str
    rationale: str = ""


@dataclass
class Candidate:
    task_id: str
    candidate: str
    source: str


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's κ for binary labels.

    κ = (p_o - p_e) / (1 - p_e), where p_o is observed agreement and p_e is
    chance agreement. Returns 0.0 if all labels degenerate.
    """
    if len(a) != len(b) or len(a) == 0:
        raise ValueError(f"length mismatch / empty: |a|={len(a)} |b|={len(b)}")
    n = len(a)
    p_o = sum(1 for x, y in zip(a, b) if x == y) / n
    pa_pos = sum(1 for x in a if x) / n
    pb_pos = sum(1 for x in b if x) / n
    p_e = pa_pos * pb_pos + (1 - pa_pos) * (1 - pb_pos)
    if abs(1 - p_e) < 1e-12:
        return 0.0
    return (p_o - p_e) / (1 - p_e)


def expected_calibration_error(
    confidences: list[float],
    outcomes: list[bool],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error.

    Bin predictions by confidence (10 equal-width bins on [0, 1]).
    For each bin: |mean(confidence) - empirical_pass_rate|, weighted by bin size.
    With N=3 majority vote, confidences land at {0.0, 1/3, 2/3, 1.0} so most
    bins are empty; that is fine — empty bins contribute zero.
    """
    if len(confidences) != len(outcomes) or len(confidences) == 0:
        raise ValueError("length mismatch / empty")
    n = len(confidences)
    edges = [i / n_bins for i in range(n_bins + 1)]
    ece = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        idxs = [
            j for j, c in enumerate(confidences)
            if (c >= lo and (c < hi or (i == n_bins - 1 and c <= hi)))
        ]
        if not idxs:
            continue
        bin_conf = sum(confidences[j] for j in idxs) / len(idxs)
        bin_acc = sum(1 for j in idxs if outcomes[j]) / len(idxs)
        ece += (len(idxs) / n) * abs(bin_conf - bin_acc)
    return ece


def load_human_labels(path: Path) -> dict[str, HumanLabel]:
    if not path.exists():
        raise FileNotFoundError(
            f"human gold labels missing: {path}\n"
            "Author them per DECISIONS.md #11 before running calibration."
        )
    out: dict[str, HumanLabel] = {}
    with path.open() as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            rec = json.loads(raw)
            for k in ("task_id", "label", "annotator_id", "timestamp"):
                if k not in rec:
                    raise ValueError(f"{path}:{lineno} missing field {k!r}")
            label_str = rec["label"].lower()
            if label_str not in ("pass", "fail"):
                raise ValueError(
                    f"{path}:{lineno} label must be 'pass' or 'fail', got {rec['label']!r}"
                )
            out[rec["task_id"]] = HumanLabel(
                task_id=rec["task_id"],
                label=(label_str == "pass"),
                annotator_id=rec["annotator_id"],
                timestamp=rec["timestamp"],
                rationale=rec.get("rationale", ""),
            )
    if not out:
        raise ValueError(f"no rows in {path}")
    return out


def load_candidates(path: Path) -> dict[str, Candidate]:
    if not path.exists():
        raise FileNotFoundError(
            f"candidates file missing: {path}\n"
            "Generate with scripts/generate_swe_qa_candidates.py first."
        )
    out: dict[str, Candidate] = {}
    with path.open() as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            rec = json.loads(raw)
            for k in ("task_id", "candidate", "source"):
                if k not in rec:
                    raise ValueError(f"{path}:{lineno} missing field {k!r}")
            out[rec["task_id"]] = Candidate(
                task_id=rec["task_id"],
                candidate=rec["candidate"],
                source=rec["source"],
            )
    return out


def calibrate(
    *,
    version: str,
    judge_model_name: str,
    n_votes: int,
    judge_run_id: Optional[str] = None,
) -> dict:
    qfile = QUESTIONS_DIR / f"v{version}" / "questions.jsonl"
    cfile = QUESTIONS_DIR / f"v{version}" / "candidates.jsonl"
    hfile = QUESTIONS_DIR / f"v{version}" / "human_labels.jsonl"

    tasks_by_id = {t.task_id: t for t in SweQaDataset(version=version, questions_path=qfile)}
    candidates = load_candidates(cfile)
    humans = load_human_labels(hfile)

    common = sorted(set(tasks_by_id) & set(candidates) & set(humans))
    if not common:
        raise ValueError(
            "no overlap between tasks, candidates, and human labels — "
            f"|tasks|={len(tasks_by_id)} |cand|={len(candidates)} |human|={len(humans)}"
        )
    if len(common) < 200:
        print(
            f"WARNING: only {len(common)} jointly labeled tasks (<200). "
            "κ estimate will be unstable; report flagged exploratory.",
            file=sys.stderr,
        )

    judge = LLMJudge(
        AnthropicModel(judge_model_name),
        n_votes=n_votes,
        judge_run_id=judge_run_id,
    )

    judge_pass: list[bool] = []
    judge_conf: list[float] = []
    human_pass: list[bool] = []
    per_task: list[dict] = []
    for tid in common:
        score = judge.score(tasks_by_id[tid], candidates[tid].candidate)
        judge_pass.append(score.correct)
        judge_conf.append(score.raw)
        human_pass.append(humans[tid].label)
        per_task.append({
            "task_id": tid,
            "human": humans[tid].label,
            "judge": score.correct,
            "confidence": score.raw,
            "annotator_id": humans[tid].annotator_id,
            "agreement": score.correct == humans[tid].label,
        })

    kappa = cohen_kappa(human_pass, judge_pass)
    ece = expected_calibration_error(judge_conf, human_pass)
    agreement = sum(1 for x in per_task if x["agreement"]) / len(per_task)

    n_pass_human = sum(human_pass)
    n_pass_judge = sum(judge_pass)

    passed_kappa = kappa >= KAPPA_PASS
    passed_ece = ece <= ECE_PASS
    well_calibrated_badge = ece <= ECE_BADGE
    overall_pass = passed_kappa and passed_ece

    report = {
        "judge_run_id": judge.judge_run_id,
        "judge_model": judge_model_name,
        "n_votes": n_votes,
        "dataset_version": version,
        "n_evaluated": len(common),
        "n_pass_human": n_pass_human,
        "n_pass_judge": n_pass_judge,
        "raw_agreement": agreement,
        "cohens_kappa": kappa,
        "ece": ece,
        "thresholds": {
            "kappa_pass": KAPPA_PASS,
            "ece_pass": ECE_PASS,
            "ece_badge": ECE_BADGE,
        },
        "verdict": {
            "kappa_pass": passed_kappa,
            "ece_pass": passed_ece,
            "well_calibrated_badge": well_calibrated_badge,
            "overall_pass": overall_pass,
        },
        "per_task": per_task,
    }
    return report


def print_summary(report: dict) -> None:
    v = report["verdict"]
    badge = " (well-calibrated)" if v["well_calibrated_badge"] else ""
    print()
    print("=" * 72)
    print(f"Judge calibration — {report['judge_run_id']}")
    print("=" * 72)
    print(f"  judge_model      : {report['judge_model']}")
    print(f"  n_votes          : {report['n_votes']}")
    print(f"  dataset_version  : {report['dataset_version']}")
    print(f"  n_evaluated      : {report['n_evaluated']}")
    print(f"  human pass-rate  : {report['n_pass_human']}/{report['n_evaluated']}"
          f" = {report['n_pass_human']/report['n_evaluated']:.3f}")
    print(f"  judge pass-rate  : {report['n_pass_judge']}/{report['n_evaluated']}"
          f" = {report['n_pass_judge']/report['n_evaluated']:.3f}")
    print(f"  raw agreement    : {report['raw_agreement']:.3f}")
    print(f"  Cohen's κ        : {report['cohens_kappa']:+.3f} "
          f"(threshold ≥ {KAPPA_PASS}) {'PASS' if v['kappa_pass'] else 'FAIL'}")
    print(f"  ECE              : {report['ece']:.4f} "
          f"(threshold ≤ {ECE_PASS}) {'PASS' if v['ece_pass'] else 'FAIL'}{badge}")
    print()
    print(f"  OVERALL          : {'PASS' if v['overall_pass'] else 'FAIL'}")
    if not v["overall_pass"]:
        print()
        print("  Per CHUNK_05_judge.md exit gate 1: SWE-QA results are EXPLORATORY only.")
        print("  Headline TPCA continues to use auto-scored datasets (needle-codebase).")
    print("=" * 72)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="1.0.0", help="SWE-QA dataset version")
    p.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                   help="Gateway-prefixed judge model id")
    p.add_argument("--n-votes", type=int, default=DEFAULT_N_VOTES,
                   help="N-way majority vote (must be odd, >= 3)")
    p.add_argument("--judge-run-id", default=None,
                   help="Override judge run id (default: random)")
    p.add_argument("--out", type=Path, default=None,
                   help="Where to write the JSON report (default: results/judge/calibration_<id>.json)")
    args = p.parse_args()

    report = calibrate(
        version=args.version,
        judge_model_name=args.judge_model,
        n_votes=args.n_votes,
        judge_run_id=args.judge_run_id,
    )
    out = args.out or REPORT_DIR / f"calibration_{report['judge_run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote report → {out}")
    print_summary(report)
    sys.exit(0 if report["verdict"]["overall_pass"] else 1)


if __name__ == "__main__":
    main()
