import math

import pytest

from tokenbench.core.metrics import (
    DEFAULT_AMORTIZATION_VOLUMES,
    IsoAccuracyPoint,
    IsoBudgetPoint,
    ParetoPoint,
    accuracy,
    bootstrap_ci,
    iso_accuracy_tokens,
    iso_budget_accuracy,
    paired_uplift_ci,
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


# ---------- paired_uplift_ci ----------


def _rec(task_id: str, repeat: int, correct: bool, provider="A") -> RunRecord:
    return RunRecord(
        task_id=task_id,
        dataset_version="1.0.0",
        harness_version="0.1.0",
        provider=ProviderRef(name=provider, version="0.0.1"),
        model="mock-1",
        repeat=repeat,
        seed=0,
        telemetry=Telemetry(input_tokens_norm=1, output_tokens_norm=1, build_tokens_norm=0),
        score=Score(correct=correct, raw=1.0 if correct else 0.0, scorer="auto_contains"),
    )


def test_paired_uplift_empty_intersection_returns_zero():
    a = [_rec("t1", 0, True, provider="A")]
    b = [_rec("t2", 0, True, provider="B")]
    u = paired_uplift_ci(a, b)
    assert u.n == 0
    assert u.mean == 0.0


def test_paired_uplift_perfect_uplift():
    a = [_rec(f"t{i}", 0, True, provider="A") for i in range(10)]
    b = [_rec(f"t{i}", 0, False, provider="B") for i in range(10)]
    u = paired_uplift_ci(a, b)
    assert u.n == 10
    assert u.mean == 1.0
    assert u.wins == 10
    assert u.losses == 0
    assert u.ties == 0
    # CI is degenerate at 1.0
    assert u.ci_low == pytest.approx(1.0)
    assert u.ci_high == pytest.approx(1.0)


def test_paired_uplift_perfect_tie():
    a = [_rec(f"t{i}", 0, True, provider="A") for i in range(8)]
    b = [_rec(f"t{i}", 0, True, provider="B") for i in range(8)]
    u = paired_uplift_ci(a, b)
    assert u.n == 8
    assert u.mean == 0.0
    assert u.ties == 8
    assert u.ci_low == pytest.approx(0.0)
    assert u.ci_high == pytest.approx(0.0)


def test_paired_uplift_intersects_on_task_and_repeat():
    """Different repeat = different pair. Drops unmatched records."""
    a = [_rec("t1", 0, True), _rec("t1", 1, False), _rec("t2", 0, True)]
    b = [_rec("t1", 0, False), _rec("t2", 0, False), _rec("t3", 0, True)]
    u = paired_uplift_ci(a, b)
    # Only (t1, 0) and (t2, 0) intersect.
    assert u.n == 2
    assert u.wins == 2
    assert u.mean == 1.0


def test_paired_uplift_partial_uplift_ci_is_well_formed():
    """5/10 wins, 0 losses → mean = 0.5; CI must be a finite ordered tuple."""
    a = [_rec(f"t{i}", 0, i < 5, provider="A") for i in range(10)]
    b = [_rec(f"t{i}", 0, False, provider="B") for i in range(10)]
    u = paired_uplift_ci(a, b, seed=42)
    assert u.n == 10
    assert u.mean == pytest.approx(0.5)
    assert u.wins == 5
    assert u.losses == 0
    assert u.ties == 5
    assert 0.0 <= u.ci_low <= u.mean <= u.ci_high <= 1.0


def test_paired_uplift_seed_is_deterministic():
    a = [_rec(f"t{i}", 0, i % 3 == 0, provider="A") for i in range(15)]
    b = [_rec(f"t{i}", 0, False, provider="B") for i in range(15)]
    u1 = paired_uplift_ci(a, b, seed=7)
    u2 = paired_uplift_ci(a, b, seed=7)
    assert u1 == u2


# ---------- iso_accuracy_tokens / iso_budget_accuracy ----------


def _multi_records(method: str, n_correct: int, n_total: int,
                   in_n: int = 100, out_n: int = 10, build_n: int = 0) -> list[RunRecord]:
    """Build n_total records for `method`; the first n_correct are correct."""
    recs = []
    for i in range(n_total):
        recs.append(RunRecord(
            task_id=f"t{i}",
            dataset_version="1.0.0",
            harness_version="0.1.0",
            provider=ProviderRef(name=method, version="0.0.1"),
            model="mock-1",
            repeat=0,
            seed=0,
            telemetry=Telemetry(input_tokens_norm=in_n, output_tokens_norm=out_n,
                                build_tokens_norm=build_n),
            score=Score(correct=(i < n_correct), raw=1.0 if i < n_correct else 0.0,
                        scorer="auto_contains"),
        ))
    return recs


def test_iso_accuracy_method_reaches_target_returns_tokens():
    recs = {"M1": _multi_records("M1", n_correct=8, n_total=10, in_n=100, out_n=10)}
    pts = iso_accuracy_tokens(recs, target_acc=0.7, V=1.0)
    assert len(pts) == 1
    assert pts[0].method == "M1"
    assert pts[0].tokens == pytest.approx(110.0)  # 100 in + 10 out, no build
    assert pts[0].acc_reached == pytest.approx(0.8)


def test_iso_accuracy_method_below_target_returns_none():
    recs = {"M1": _multi_records("M1", n_correct=5, n_total=10)}
    pts = iso_accuracy_tokens(recs, target_acc=0.9, V=1.0)
    assert pts[0].tokens is None
    assert pts[0].acc_reached == pytest.approx(0.5)


def test_iso_accuracy_amortizes_build_at_higher_V():
    # build_n=1000 dominates at V=1, vanishes at V=10000
    recs = {"M1": _multi_records("M1", n_correct=10, n_total=10,
                                 in_n=100, out_n=10, build_n=1000)}
    p1 = iso_accuracy_tokens(recs, target_acc=0.5, V=1.0)[0]
    p10k = iso_accuracy_tokens(recs, target_acc=0.5, V=10_000.0)[0]
    # V=1: 100+10+1000/1 = 1110; V=10k: 100+10+1000/10k ≈ 110.1
    assert p1.tokens == pytest.approx(1110.0)
    assert p10k.tokens == pytest.approx(110.1)


def test_iso_accuracy_handles_multiple_methods():
    recs = {
        "M1": _multi_records("M1", n_correct=10, n_total=10, in_n=200, out_n=20),
        "M2": _multi_records("M2", n_correct=4, n_total=10, in_n=100, out_n=10),
    }
    pts = {p.method: p for p in iso_accuracy_tokens(recs, target_acc=0.5, V=1.0)}
    assert pts["M1"].tokens == pytest.approx(220.0)  # reaches 1.0 at 220 tokens
    assert pts["M2"].tokens is None                   # only 0.4, below 0.5
    assert pts["M2"].acc_reached == pytest.approx(0.4)


def test_iso_accuracy_skips_empty_method():
    recs = {"M1": _multi_records("M1", 5, 10), "M2": []}
    pts = iso_accuracy_tokens(recs, target_acc=0.4, V=1.0)
    methods = {p.method for p in pts}
    assert methods == {"M1"}  # M2 dropped


def test_iso_budget_method_under_budget_reports_observed_acc():
    recs = {"M1": _multi_records("M1", n_correct=7, n_total=10, in_n=100, out_n=10)}
    pts = iso_budget_accuracy(recs, budget_tokens=200.0, V=1.0)
    assert len(pts) == 1
    assert pts[0].feasible is True
    assert pts[0].accuracy == pytest.approx(0.7)
    assert pts[0].tokens_used == pytest.approx(110.0)


def test_iso_budget_method_over_budget_marked_infeasible():
    recs = {"M1": _multi_records("M1", n_correct=7, n_total=10, in_n=10_000, out_n=100)}
    pts = iso_budget_accuracy(recs, budget_tokens=1_000.0, V=1.0)
    assert pts[0].feasible is False
    assert pts[0].accuracy == 0.0
    assert pts[0].tokens_used == pytest.approx(10_100.0)


def test_iso_budget_amortization_can_make_method_feasible():
    """At V=1 the method's build cost blows the budget; at V=10000 it fits."""
    recs = {"M1": _multi_records("M1", n_correct=8, n_total=10,
                                 in_n=100, out_n=10, build_n=1_000_000)}
    p1 = iso_budget_accuracy(recs, budget_tokens=10_000.0, V=1.0)[0]
    p10k = iso_budget_accuracy(recs, budget_tokens=10_000.0, V=10_000.0)[0]
    assert p1.feasible is False     # 100 + 10 + 1_000_000 > 10_000
    assert p10k.feasible is True    # 100 + 10 + 100 = 210 <= 10_000
    assert p10k.accuracy == pytest.approx(0.8)


def test_iso_accuracy_point_is_immutable():
    p = IsoAccuracyPoint(method="M", target_acc=0.7, V=1.0, tokens=100.0, acc_reached=0.8)
    with pytest.raises(Exception):  # FrozenInstanceError
        p.tokens = 50.0  # type: ignore[misc]
