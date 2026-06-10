import math

import pytest

from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    ParetoPoint,
    accuracy,
    bootstrap_ci,
    pareto_frontier,
    per_record_tokens,
    summarize,
    tpca,
    tpca_curve,
)
from tokenbench.core.schemas import (
    ProviderRef,
    RunRecord,
    Score,
    Telemetry,
)


def make_record(*, correct: bool, in_n: int, out_n: int, build_n: int = 0) -> RunRecord:
    return RunRecord(
        task_id="t",
        dataset_version="1.0.0",
        harness_version="0.1.0",
        provider=ProviderRef(name="mock", version="0.0.1"),
        model="mock-1",
        repeat=0,
        seed=0,
        telemetry=Telemetry(
            input_tokens_norm=in_n,
            output_tokens_norm=out_n,
            build_tokens_norm=build_n,
        ),
        score=Score(correct=correct, raw=1.0 if correct else 0.0, scorer="auto_contains"),
    )


def test_tpca_simple_no_build():
    recs = [
        make_record(correct=True, in_n=100, out_n=10),
        make_record(correct=True, in_n=200, out_n=20),
    ]
    # 330 tokens / 2 correct = 165
    assert tpca(recs, V=1) == 165.0


def test_tpca_returns_inf_when_no_correct():
    recs = [make_record(correct=False, in_n=100, out_n=10)]
    assert tpca(recs, V=1) == math.inf


def test_tpca_amortization_curve_decreases_with_V():
    # one record with non-trivial build cost
    recs = [make_record(correct=True, in_n=100, out_n=10, build_n=10_000)]
    curve = tpca_curve(recs, volumes=[1, 100, 10_000])
    # V=1: 100 + 10 + 10000/1     = 10110
    # V=100: 100 + 10 + 10000/100 = 210
    # V=10k: 100 + 10 + 10000/10k = 111
    assert curve[1] == pytest.approx(10_110)
    assert curve[100] == pytest.approx(210)
    assert curve[10_000] == pytest.approx(111)
    # monotonic decreasing
    assert curve[1] > curve[100] > curve[10_000]


def test_tpca_default_volumes_match_decisions_md():
    assert DEFAULT_AMORTIZATION_VOLUMES == (1, 100, 10_000)


def test_tpca_rejects_non_positive_V():
    recs = [make_record(correct=True, in_n=10, out_n=1)]
    with pytest.raises(ValueError):
        tpca(recs, V=0)


def test_tpca_empty_raises():
    with pytest.raises(ValueError):
        tpca([], V=1)


def test_accuracy():
    recs = [
        make_record(correct=True, in_n=10, out_n=1),
        make_record(correct=False, in_n=10, out_n=1),
        make_record(correct=True, in_n=10, out_n=1),
    ]
    assert accuracy(recs) == pytest.approx(2 / 3)


def test_per_record_tokens_includes_amortized_build():
    recs = [
        make_record(correct=True, in_n=100, out_n=0, build_n=200),
        make_record(correct=True, in_n=100, out_n=0, build_n=200),
    ]
    # at V=2: each record sees 100 + 0 + 200/2 = 200
    vals = per_record_tokens(recs, V=2)
    assert vals == [200.0, 200.0]


def test_summarize_handles_heavy_tail():
    # heavy-tailed sample: median should be far from mean
    vals = [1.0] * 10 + [1000.0]
    s = summarize(vals)
    assert s.median == 1.0
    assert s.mean > 50.0  # mean is dragged by the tail
    assert s.iqr == 0.0  # all the mass is at 1.0


def test_summarize_empty():
    s = summarize([])
    assert s.n == 0


def test_bootstrap_ci_contains_true_mean_for_easy_data():
    # all values 5.0 — CI should be (5.0, 5.0)
    low, high = bootstrap_ci([5.0] * 50, n_resamples=200, seed=1)
    assert low == 5.0 and high == 5.0


def test_bootstrap_ci_widens_with_variance():
    tight_low, tight_high = bootstrap_ci([5.0] * 50 + [5.1] * 50, seed=1)
    wide_low, wide_high = bootstrap_ci([1.0, 5.0, 9.0] * 30, seed=1)
    assert (wide_high - wide_low) > (tight_high - tight_low)


def test_pareto_frontier_basic():
    # method A: low tokens, low acc
    # method B: high tokens, high acc
    # method C: dominated by B
    pts = [
        ParetoPoint("A", accuracy=0.5, tokens_per_query=100),
        ParetoPoint("B", accuracy=0.9, tokens_per_query=300),
        ParetoPoint("C", accuracy=0.7, tokens_per_query=400),  # worse than B on both
    ]
    frontier = pareto_frontier(pts)
    names = {p.method for p in frontier}
    assert names == {"A", "B"}


def test_pareto_frontier_keeps_tied_points():
    # two points with same tokens, same accuracy: neither strictly dominates
    # the other, so both stay on the frontier.
    pts = [
        ParetoPoint("A", accuracy=0.5, tokens_per_query=100),
        ParetoPoint("B", accuracy=0.5, tokens_per_query=100),
    ]
    frontier = pareto_frontier(pts)
    assert len(frontier) == 2
    assert {p.method for p in frontier} == {"A", "B"}
