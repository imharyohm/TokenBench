"""Append-only run-record store. Per DECISIONS.md #4.

JSONL is the canonical write target. Chunk 4 adds:
  - thread-safe appends (parallel runner)
  - completed_keys() for idempotent re-runs (skip cells already recorded)
  - SQLite mirror via `tokenbench.results.sqlite_store.SQLiteStore`
  - Parquet exports via `scripts/export_parquet.py`

The cell key is `(task_id, provider_name, provider_version, model, repeat, seed,
dataset_version, harness_version)`. Two records with the same key are the same
cell — a clean run and a kill+resume run will produce the same key set even
though run_ids and timestamps differ (per Chunk 4 exit gates 2 and 3).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterator, Optional, Tuple

from ..core.schemas import RunRecord


CellKey = Tuple[str, str, str, str, int, int, str, str]
# (task_id, provider_name, provider_version, model, repeat, seed,
#  dataset_version, harness_version)


def cell_key(record: RunRecord) -> CellKey:
    return (
        record.task_id,
        record.provider.name,
        record.provider.version,
        record.model,
        record.repeat,
        record.seed,
        record.dataset_version,
        record.harness_version,
    )


class ResultsStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._lock = threading.Lock()

    def append(self, record: RunRecord) -> None:
        line = record.model_dump_json()
        # Single-line JSONL appends serialised across threads. POSIX append
        # mode is per-write atomic for small payloads, but we lock anyway so
        # behaviour is consistent across platforms (notably Windows).
        with self._lock, self.path.open("a") as f:
            f.write(line + "\n")

    def all(self) -> Iterator[RunRecord]:
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield RunRecord.model_validate_json(line)

    def completed_keys(
        self,
        *,
        dataset_version: Optional[str] = None,
        harness_version: Optional[str] = None,
    ) -> set[CellKey]:
        """Return the set of cell keys already in the store.

        Used by Runner to skip cells that have already been scored.
        Optionally filter by dataset/harness version so cells from a
        prior version don't shadow a fresh run.
        """
        keys: set[CellKey] = set()
        for r in self.all():
            if dataset_version is not None and r.dataset_version != dataset_version:
                continue
            if harness_version is not None and r.harness_version != harness_version:
                continue
            keys.add(cell_key(r))
        return keys

    def filter(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> list[RunRecord]:
        out = []
        for r in self.all():
            if provider is not None and r.provider.name != provider:
                continue
            if model is not None and r.model != model:
                continue
            if dataset_version is not None and r.dataset_version != dataset_version:
                continue
            out.append(r)
        return out
