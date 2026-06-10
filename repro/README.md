# TokenBench — Reproducibility Package

This directory is the entrypoint for someone who has just cloned the repo
and wants to reproduce a published result. The stranger test in Chunk 4
exit gate #1 walks through these exact commands.

## What you need

- Python 3.14 (matches `.venv/`; lockfile is pinned to this minor)
- `git` on `PATH` (snapshot script clones the pinned repos)
- A gateway token for the Anthropic-format API in `.env` at the repo root:
  ```
  ANTHROPIC_BASE_URL="https://<your-gateway>"
  ANTHROPIC_AUTH_TOKEN="sk-..."
  ```
- (Optional, for the Docker exit gate) Docker Desktop running

## One-command reproduction

```bash
cd repro
make repro TASK=needle-click-0000
```

This will:

1. Create a `.venv` and install **pinned** deps from `requirements.lock.txt`.
2. Pull each pinned repo at its exact commit into `artifacts/repos/<short_id>/`.
3. Re-hash each snapshot and reject any tampered tree.
4. Run the cell once and print its `RunRecord` (JSON).

Compare the `telemetry.input_tokens_norm` field in the output against the
published number in `results/findings/CHUNK_03_findings.md`. Per exit gate
#1, the match must be within **~1%** (the small drift comes from gateway-
side model nondeterminism on the output, not the deterministic input).

## Subset commands

```bash
make install        # venv + pinned deps only
make snapshot       # clone + content-address pinned repos
make verify         # re-hash snapshots and compare
make docker         # build snapshot containers (requires daemon)
make run-cell TASK=needle-click-0000   # assumes install/verify already done
```

## Resume / parallel sweeps

The runner upgrade in Chunk 4 makes sweeps idempotent and resumable:

- Re-running a sweep skips cells already in the store (no extra spend).
- Killing mid-sweep and re-running picks up from the last persisted cell.
- `RunConfig(concurrency=N)` runs cells in parallel via threads.

See `tokenbench/runner/engine.py` for the cell key
`(task_id, provider_version, model, repeat, seed, dataset_version, harness_version)`
that drives idempotency.

## Storage layout

- **JSONL** (`results/runs/*.jsonl`) — canonical, append-only, immutable.
- **SQLite** (`results/runs/*.db`) — derived mirror, queryable via
  `tokenbench.results.sqlite_store.SQLiteStore`.
- **Parquet** (`results/runs/*.parquet`) — derived export for sharing,
  built by `python scripts/export_parquet.py <jsonl_path>` (requires
  `pyarrow`).

You only ever write to JSONL. The other two are regenerable.

## Snapshot integrity

Snapshot byproducts (`graphify-out/`, `__pycache__/`, …) are excluded
from `snapshot_sha256` hashing — see
`tokenbench/datasets/repo_pins.py:SNAPSHOT_EXCLUDE_DIRS`. This keeps the
hash stable when downstream tools mutate the tree.

## Known caveats

- `aider-chat` upstream cannot install on Python 3.14 (`pkgutil.ImpImporter`
  removal). The `repo-map` provider implements aider-style on
  `tree-sitter`+`ast` directly — see
  `tokenbench/providers/repo_map.py:FROZEN_CONFIG.provenance`. This is a
  documented frozen-config substitution; faithful to the approach, not
  the literal package.
