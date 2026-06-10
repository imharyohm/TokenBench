"""Tests for the SQLite mirror + query API (Chunk 4 deliverable #4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tokenbench.datasets.mock import MockDataset
from tokenbench.judges.auto_contains import AutoContainsJudge
from tokenbench.models.mock import MockModel
from tokenbench.providers.mock import MockRAGProvider
from tokenbench.results.sqlite_store import SQLiteStore
from tokenbench.results.store import ResultsStore
from tokenbench.runner.engine import RunConfig, Runner


def _seed_store(jsonl_path: Path):
    store = ResultsStore(jsonl_path)
    Runner(store).sweep(
        dataset=MockDataset(n_tasks=3),
        providers=[MockRAGProvider()],
        models=[MockModel(correctness_rate=1.0)],
        judge=AutoContainsJudge(),
        config=RunConfig(repeats=2, base_seed=1),
    )
    return store


def test_mirror_round_trips_all_records():
    with tempfile.TemporaryDirectory() as td:
        jsonl = Path(td) / "runs.jsonl"
        store = _seed_store(jsonl)
        n_jsonl = sum(1 for _ in store.all())

        with SQLiteStore.from_jsonl(store) as mirror:
            assert mirror.count() == n_jsonl
            rows = mirror.query()
            assert len(rows) == n_jsonl
            assert all("run_id" in r for r in rows)


def test_query_filters_by_provider_model_dataset_version():
    with tempfile.TemporaryDirectory() as td:
        jsonl = Path(td) / "runs.jsonl"
        store = _seed_store(jsonl)
        with SQLiteStore.from_jsonl(store) as mirror:
            rows_all = mirror.query()
            rows_provider = mirror.query(provider="mock-rag")
            rows_other = mirror.query(provider="not-a-provider")
            assert len(rows_provider) == len(rows_all)
            assert rows_other == []

            sample = rows_all[0]
            rows_pm = mirror.query(
                provider=sample["provider_name"],
                model=sample["model"],
                dataset_version=sample["dataset_version"],
            )
            assert len(rows_pm) == len(rows_all)


def test_ingest_is_idempotent():
    """Re-ingesting the same JSONL twice does not duplicate rows."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = Path(td) / "runs.jsonl"
        store = _seed_store(jsonl)
        sqlite_path = Path(td) / "runs.db"

        first = SQLiteStore(sqlite_path)
        first.ingest(store)
        n1 = first.count()
        # Re-ingest the same JSONL contents.
        added = first.ingest(store)
        assert added == 0
        assert first.count() == n1
        first.close()


def test_jsonl_remains_canonical_when_mirror_built():
    """Building the SQLite mirror must not modify the JSONL file."""
    with tempfile.TemporaryDirectory() as td:
        jsonl = Path(td) / "runs.jsonl"
        store = _seed_store(jsonl)
        before = jsonl.read_bytes()
        with SQLiteStore.from_jsonl(store):
            pass
        after = jsonl.read_bytes()
        assert before == after
