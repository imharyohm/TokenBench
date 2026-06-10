import tempfile
from pathlib import Path

from tokenbench.datasets.mock import MockDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.mock import MockModel
from tokenbench.providers.mock import MockRAGProvider
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner, cells_count


def test_sweep_writes_records():
    with tempfile.TemporaryDirectory() as td:
        store = ResultsStore(Path(td) / "runs.jsonl")
        runner = Runner(store)
        records = runner.sweep(
            dataset=MockDataset(n_tasks=5),
            providers=[MockRAGProvider()],
            models=[MockModel(correctness_rate=1.0)],
            judge=AutoContainsJudge(),
            config=RunConfig(repeats=2),
        )
        assert len(records) == 5 * 2  # tasks * repeats
        # store round-trips
        assert len(list(store.all())) == 5 * 2
        # all correct (rate=1.0)
        assert all(r.score.correct for r in records)


def test_seeded_runs_are_deterministic():
    with tempfile.TemporaryDirectory() as td:
        store_a = ResultsStore(Path(td) / "a.jsonl")
        store_b = ResultsStore(Path(td) / "b.jsonl")
        runner_a, runner_b = Runner(store_a), Runner(store_b)

        kwargs = dict(
            dataset=MockDataset(n_tasks=3),
            providers=[MockRAGProvider()],
            models=[MockModel(correctness_rate=0.5)],
            judge=AutoContainsJudge(),
            config=RunConfig(repeats=2, base_seed=99),
        )
        records_a = runner_a.sweep(**kwargs)
        records_b = runner_b.sweep(**kwargs)
        # same correctness pattern across runs with same seed
        assert [r.score.correct for r in records_a] == [r.score.correct for r in records_b]


def test_cells_count():
    assert cells_count(100, 4, 2, 5) == 4000
