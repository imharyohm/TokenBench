"""Chunk 4 runner upgrade — idempotent · resumable · parallel."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tokenbench.datasets.mock import MockDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.mock import MockModel
from tokenbench.providers.mock import MockRAGProvider
from tokenbench.results.store import ResultsStore, cell_key
from tokenbench.runner.engine import RunConfig, Runner


def _make_kwargs(seed=99, repeats=2, concurrency=1):
    return dict(
        dataset=MockDataset(n_tasks=4),
        providers=[MockRAGProvider()],
        models=[MockModel(correctness_rate=1.0)],
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=repeats, base_seed=seed, concurrency=concurrency),
    )


def test_idempotent_rerun_is_a_noop():
    """Running the same sweep twice on the same store must add 0 records."""
    with tempfile.TemporaryDirectory() as td:
        store = ResultsStore(Path(td) / "runs.jsonl")
        first = Runner(store).sweep(**_make_kwargs())
        n_after_first = sum(1 for _ in store.all())
        assert n_after_first == 4 * 2  # tasks * repeats

        skipped: list = []
        second = Runner(store).sweep(**_make_kwargs(), on_skip=skipped.append)
        n_after_second = sum(1 for _ in store.all())
        assert n_after_second == n_after_first
        assert second == []  # nothing newly executed
        assert len(skipped) == 4 * 2

        # cell-key sets identical to first run
        assert {cell_key(r) for r in first} == {cell_key(r) for r in store.all()}


def test_resume_after_partial_run_matches_clean_run():
    """Exit gate #2: a kill+resume produces the same final cell-key set
    as a clean uninterrupted run."""
    with tempfile.TemporaryDirectory() as td:
        # Clean reference run.
        ref_store = ResultsStore(Path(td) / "ref.jsonl")
        ref_records = Runner(ref_store).sweep(**_make_kwargs())
        ref_keys = {cell_key(r) for r in ref_records}

        # Simulate partial run: record only the first half of cells in the
        # store, then resume with a fresh runner.
        partial_store = ResultsStore(Path(td) / "partial.jsonl")
        for r in ref_records[: len(ref_records) // 2]:
            partial_store.append(r)

        resumed = Runner(partial_store).sweep(**_make_kwargs())
        resumed_keys = {cell_key(r) for r in resumed}
        # Resumed run only executes the missing half.
        assert resumed_keys == ref_keys - {cell_key(r) for r in ref_records[: len(ref_records) // 2]}

        # Final store contents match the reference.
        final_keys = {cell_key(r) for r in partial_store.all()}
        assert final_keys == ref_keys


def test_parallel_run_produces_same_cell_keys_as_sequential():
    """Exit gate #3: two parallel runs against the same dataset version
    produce identical run records (modulo run_ids and timestamps).

    Cell keys are the byte-identity check; run_id/timestamp are excluded
    from the key by construction.
    """
    with tempfile.TemporaryDirectory() as td:
        seq_store = ResultsStore(Path(td) / "seq.jsonl")
        par_store = ResultsStore(Path(td) / "par.jsonl")

        seq = Runner(seq_store).sweep(**_make_kwargs(concurrency=1))
        par = Runner(par_store).sweep(**_make_kwargs(concurrency=4))

        assert {cell_key(r) for r in seq} == {cell_key(r) for r in par}

        # Telemetry deterministic on the mock model.
        seq_by_key = {cell_key(r): r for r in seq}
        par_by_key = {cell_key(r): r for r in par}
        for k, r in seq_by_key.items():
            p = par_by_key[k]
            assert r.telemetry.input_tokens_norm == p.telemetry.input_tokens_norm
            assert r.telemetry.output_tokens_norm == p.telemetry.output_tokens_norm
            assert r.score.correct == p.score.correct


def test_provider_build_memoised_across_repeats():
    """Build runs once per (provider, task), not once per cell."""
    builds: list[str] = []

    class CountingRAG(MockRAGProvider):
        def build(self, task):
            builds.append(task.task_id)
            return super().build(task)

    with tempfile.TemporaryDirectory() as td:
        store = ResultsStore(Path(td) / "runs.jsonl")
        Runner(store).sweep(
            dataset=MockDataset(n_tasks=3),
            providers=[CountingRAG()],
            models=[MockModel(correctness_rate=1.0)],
            judge=AutoContainsJudge(),
            config=RunConfig(repeats=4, base_seed=0),
        )
    # 3 tasks × 4 repeats = 12 cells, but only 3 builds.
    assert sorted(builds) == sorted({f"mock-{i:04d}" for i in range(3)})
