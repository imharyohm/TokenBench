"""Primary and secondary metrics. Per §0.1 of tokenbench_architecture.md.

Headline number: TPCA(V) — tokens per correct answer at amortization volume V.
Headline visual: Pareto frontier of (accuracy, tokens).
Token usage is heavy-tailed: report median + IQR, never just the mean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .schemas import RunRecord

DEFAULT_AMORTIZATION_VOLUMES = (1, 100, 10_000)


def _tokens_for_record(rec: RunRecord, V: float) -> float:
    """Per-attempt tokens, with build cost amortized over V queries.

    tokens(m, t, r, V) = input_norm + output_norm + (build_norm / V)
    """
    if V <= 0:
        raise ValueError("amortization volume V must be > 0")
    t = rec.telemetry
    build_share = t.build_tokens_norm / V if math.isfinite(V) else 0.0
    return float(t.input_tokens_norm + t.output_tokens_norm + build_share)


def tpca(records: Sequence[RunRecord], V: float) -> float:
    """TPCA(m, V) = Σ tokens / Σ correct.

    Returns +inf if no records are correct (the metric is undefined and
    callers must handle this — typically by reporting "N correct = 0".)
    """
    if not records:
        raise ValueError("tpca requires at least one record")
    total_tokens = sum(_tokens_for_record(r, V) for r in records)
    total_correct = sum(1 for r in records if r.score.correct)
    if total_correct == 0:
        return math.inf
    return total_tokens / total_correct


def tpca_curve(
    records: Sequence[RunRecord],
    volumes: Iterable[float] = DEFAULT_AMORTIZATION_VOLUMES,
) -> dict[float, float]:
    """TPCA at each amortization volume V. The mandatory reporting form for
    methods with non-zero build cost (DECISIONS.md #5)."""
    return {V: tpca(records, V) for V in volumes}


def accuracy(records: Sequence[RunRecord]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.score.correct) / len(records)


def total_tokens(records: Sequence[RunRecord], V: float) -> float:
    return sum(_tokens_for_record(r, V) for r in records)


def per_record_tokens(records: Sequence[RunRecord], V: float) -> list[float]:
    return [_tokens_for_record(r, V) for r in records]


@dataclass(frozen=True)
class Distribution:
    """Heavy-tailed-aware summary. Mean + median + IQR + sample count."""

    n: int
    mean: float
    median: float
    q25: float
    q75: float

    @property
    def iqr(self) -> float:
        return self.q75 - self.q25


def summarize(values: Sequence[float]) -> Distribution:
    if not values:
        return Distribution(n=0, mean=0.0, median=0.0, q25=0.0, q75=0.0)
    arr = np.asarray(values, dtype=float)
    return Distribution(
        n=len(arr),
        mean=float(arr.mean()),
        median=float(np.median(arr)),
        q25=float(np.percentile(arr, 25)),
        q75=float(np.percentile(arr, 75)),
    )


def bootstrap_ci(
    values: Sequence[float],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI on the mean. Used for cross-task TPCA comparisons.

    Returns (low, high). For an empty input returns (0.0, 0.0)."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(arr), size=(n_resamples, len(arr)))
    means = arr[idx].mean(axis=1)
    alpha = (1 - confidence) / 2
    return (
        float(np.quantile(means, alpha)),
        float(np.quantile(means, 1 - alpha)),
    )


@dataclass(frozen=True)
class PairedUplift:
    """Paired accuracy uplift of `a` over `b`, on the SAME (task, repeat) pairs.

    `n` is the number of paired observations after intersection. `mean` is
    `mean(correct_a - correct_b)` per pair (range [-1, +1]). `ci` is a
    percentile bootstrap CI on that mean. `wins` / `ties` / `losses` count
    pairs where `a > b` / `a == b` / `a < b`.
    """
    n: int
    mean: float
    ci_low: float
    ci_high: float
    wins: int
    ties: int
    losses: int


def paired_uplift_ci(
    records_a: Sequence[RunRecord],
    records_b: Sequence[RunRecord],
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> PairedUplift:
    """Paired bootstrap on `acc(a) - acc(b)` over the (task_id, repeat) pairs
    that appear in BOTH inputs. Records that don't have a partner are dropped.

    Used to verify Chunk 6 exit gate 2 (exploit baseline must not exceed the
    priors-only floor by more than a documented tolerance) without confounding
    "the model knows public Python" with "the harness leaked gold."
    """
    a_map = {(r.task_id, r.repeat): int(r.score.correct) for r in records_a}
    b_map = {(r.task_id, r.repeat): int(r.score.correct) for r in records_b}
    keys = sorted(set(a_map) & set(b_map))
    if not keys:
        return PairedUplift(0, 0.0, 0.0, 0.0, 0, 0, 0)
    diffs = np.array([a_map[k] - b_map[k] for k in keys], dtype=float)
    wins = int((diffs > 0).sum())
    losses = int((diffs < 0).sum())
    ties = int((diffs == 0).sum())
    rng = np.random.default_rng(seed)
    n = len(diffs)
    idx = rng.integers(0, n, size=(n_resamples, n))
    boots = diffs[idx].mean(axis=1)
    alpha = (1 - confidence) / 2
    return PairedUplift(
        n=n,
        mean=float(diffs.mean()),
        ci_low=float(np.quantile(boots, alpha)),
        ci_high=float(np.quantile(boots, 1 - alpha)),
        wins=wins,
        ties=ties,
        losses=losses,
    )


@dataclass(frozen=True)
class IsoAccuracyPoint:
    """Tokens needed (per query, at amortization V) for a method to reach
    a target accuracy.

    `tokens` is None when the method never reached `target_acc`; in that
    case `acc_reached` records the highest accuracy the method actually
    achieved on this set of records, so plots can render an under-target
    marker rather than a hole.
    """
    method: str
    target_acc: float
    V: float
    tokens: float | None
    acc_reached: float


@dataclass(frozen=True)
class IsoBudgetPoint:
    """Accuracy a method reaches when its per-query tokens (at amortization
    V) are constrained to `budget_tokens`.

    `feasible=False` means the method's tokens/query exceeds the budget
    even after amortization, so accuracy at this budget is undefined.
    """
    method: str
    budget_tokens: float
    V: float
    accuracy: float
    tokens_used: float
    feasible: bool


def iso_accuracy_tokens(
    records_by_method: dict[str, Sequence[RunRecord]],
    target_acc: float,
    *,
    V: float = 1.0,
) -> list[IsoAccuracyPoint]:
    """For each method, return the tokens/query (at amortization V) needed
    to reach `target_acc`, or None if the method never gets there.

    Static methods produce a single (acc, tokens) point at any given V (no
    knob to tune), so "reaches the target" is binary: did the method's
    accuracy on this record set hit target_acc?

    This is the simplest faithful definition for v1.0's static-only
    provider lineup. Once an agentic provider lands (G, deferred to v1.1),
    this signature will need an "iso curve" — accuracy as a function of
    the agent's compute budget — and the function will return a curve
    rather than a single point.
    """
    out: list[IsoAccuracyPoint] = []
    for name in sorted(records_by_method):
        recs = list(records_by_method[name])
        if not recs:
            continue
        acc = accuracy(recs)
        per = per_record_tokens(recs, V=V)
        mean_tokens = float(np.mean(per)) if per else 0.0
        if acc >= target_acc:
            out.append(IsoAccuracyPoint(
                method=name, target_acc=target_acc, V=V,
                tokens=mean_tokens, acc_reached=acc,
            ))
        else:
            out.append(IsoAccuracyPoint(
                method=name, target_acc=target_acc, V=V,
                tokens=None, acc_reached=acc,
            ))
    return out


def iso_budget_accuracy(
    records_by_method: dict[str, Sequence[RunRecord]],
    budget_tokens: float,
    *,
    V: float = 1.0,
) -> list[IsoBudgetPoint]:
    """For each method, report the accuracy reached when per-query tokens
    (at amortization V) are constrained to `budget_tokens`.

    For static methods, tokens/query at fixed V is a method property, not
    a tunable knob — so the result is `feasible=True, accuracy=<observed>`
    if `mean_tokens <= budget`, else `feasible=False`.

    This is the operational complement of iso-accuracy: instead of "how
    many tokens to reach acc?", "what acc fits in this many tokens?" Both
    are reported alongside the headline TPCA curve.
    """
    out: list[IsoBudgetPoint] = []
    for name in sorted(records_by_method):
        recs = list(records_by_method[name])
        if not recs:
            continue
        acc = accuracy(recs)
        per = per_record_tokens(recs, V=V)
        mean_tokens = float(np.mean(per)) if per else 0.0
        feasible = mean_tokens <= budget_tokens
        out.append(IsoBudgetPoint(
            method=name, budget_tokens=budget_tokens, V=V,
            accuracy=acc if feasible else 0.0,
            tokens_used=mean_tokens, feasible=feasible,
        ))
    return out


@dataclass(frozen=True)
class ParetoPoint:
    method: str
    accuracy: float
    tokens_per_query: float  # mean tokens over records (at the chosen V)


def pareto_frontier(points: Sequence[ParetoPoint]) -> list[ParetoPoint]:
    """The accuracy-vs-tokens Pareto frontier. Higher accuracy is better,
    fewer tokens is better. Returns the non-dominated set, sorted by tokens
    ascending."""
    frontier: list[ParetoPoint] = []
    for p in sorted(points, key=lambda x: (x.tokens_per_query, -x.accuracy)):
        if any(
            (q.tokens_per_query <= p.tokens_per_query and q.accuracy >= p.accuracy)
            and (q.tokens_per_query < p.tokens_per_query or q.accuracy > p.accuracy)
            for q in frontier
        ):
            continue
        frontier.append(p)
    return frontier
