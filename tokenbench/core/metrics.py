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
