"""SQLite mirror of the JSONL run-record store (Chunk 4 deliverable #4).

JSONL remains the canonical write target — flat, append-only, easy to diff,
easy to share. SQLite is a *queryable mirror*: rebuilt from the JSONL on
demand, never written to without the JSONL being written first. This keeps
one source of truth and avoids dual-write divergence.

Why mirror at all? Because Chunk 4 spec requires a `results.query(...)` API
for leaderboard regen, and JSONL scans grow O(N) with sweep history.
SQLite gives us indexed lookups by `(provider_name, model, dataset_version)`.

Usage:
    store = ResultsStore("results/runs/chunk3.jsonl")
    sqlite = SQLiteStore.from_jsonl(store)
    rows = sqlite.query(provider="rag-bm25", model="bedrock.anthropic.claude-sonnet-4-5")
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from ..core.schemas import RunRecord
from .store import ResultsStore


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    task_id           TEXT NOT NULL,
    dataset_version   TEXT NOT NULL,
    harness_version   TEXT NOT NULL,
    provider_name     TEXT NOT NULL,
    provider_version  TEXT NOT NULL,
    provider_config   TEXT NOT NULL,        -- JSON
    model             TEXT NOT NULL,
    repeat            INTEGER NOT NULL,
    seed              INTEGER NOT NULL,
    input_tokens_norm INTEGER NOT NULL,
    output_tokens_norm INTEGER NOT NULL,
    cache_tokens_norm INTEGER NOT NULL,
    build_tokens_norm INTEGER NOT NULL,
    native_input      INTEGER NOT NULL,
    native_output     INTEGER NOT NULL,
    latency_ms        INTEGER NOT NULL,
    trace_uri         TEXT,
    score_correct     INTEGER NOT NULL,     -- 0/1
    score_raw         REAL NOT NULL,
    score_scorer      TEXT NOT NULL,
    timestamp         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_provider_model
    ON runs(provider_name, model, dataset_version);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
"""


def _row_from_record(r: RunRecord) -> tuple:
    return (
        r.run_id,
        r.task_id,
        r.dataset_version,
        r.harness_version,
        r.provider.name,
        r.provider.version,
        json.dumps(r.provider.config, sort_keys=True),
        r.model,
        r.repeat,
        r.seed,
        r.telemetry.input_tokens_norm,
        r.telemetry.output_tokens_norm,
        r.telemetry.cache_tokens_norm,
        r.telemetry.build_tokens_norm,
        r.telemetry.native_input,
        r.telemetry.native_output,
        r.telemetry.latency_ms,
        r.telemetry.trace_uri,
        1 if r.score.correct else 0,
        r.score.raw,
        r.score.scorer,
        r.timestamp.isoformat(),
    )


class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @classmethod
    def from_jsonl(cls, jsonl: ResultsStore, sqlite_path: str | Path | None = None) -> "SQLiteStore":
        """Build (or refresh) a SQLite mirror from the JSONL store.

        Default path co-locates the .db next to the .jsonl
        (e.g. chunk3.jsonl -> chunk3.db).
        Existing rows are preserved; new run_ids are inserted. Run records
        are immutable per DECISIONS.md #4, so we never UPDATE.
        """
        target = Path(sqlite_path) if sqlite_path else jsonl.path.with_suffix(".db")
        store = cls(target)
        store.ingest(jsonl)
        return store

    def ingest(self, jsonl: ResultsStore) -> int:
        """Insert any records from `jsonl` not already in the mirror.

        Returns the count of newly-inserted rows.
        """
        existing = {row[0] for row in self._conn.execute("SELECT run_id FROM runs")}
        rows = []
        for r in jsonl.all():
            if r.run_id in existing:
                continue
            rows.append(_row_from_record(r))
        if rows:
            self._conn.executemany(
                "INSERT INTO runs VALUES (" + ",".join(["?"] * 22) + ")",
                rows,
            )
            self._conn.commit()
        return len(rows)

    def query(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        dataset_version: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> list[dict]:
        """The leaderboard-regen query API specified in CHUNK_04.md §4."""
        sql = "SELECT * FROM runs WHERE 1=1"
        params: list = []
        if provider is not None:
            sql += " AND provider_name = ?"
            params.append(provider)
        if model is not None:
            sql += " AND model = ?"
            params.append(model)
        if dataset_version is not None:
            sql += " AND dataset_version = ?"
            params.append(dataset_version)
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY timestamp"
        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *_) -> None:
        self.close()
