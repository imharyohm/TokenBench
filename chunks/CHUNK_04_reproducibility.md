# Chunk 4 — Reproducibility Hardening (P4)

> Maps to: §3 P4, §1[2][5][9], §2 (irreproducibility row), §5 #4

## Goal
Make every result regenerable from a clean checkout by a stranger. This is the gate between "research code" and "benchmark."

## Entry gate
Chunk 3 passed: multiple providers producing real numbers; Pareto curve exists.

## Deliverables

### 1. Pinned environments
- Each task carries `repo.commit` + `repo.snapshot_sha256`
- A snapshot service: `scripts/snapshot_repo.py <url> <commit>` → tarball + sha256 + push to artifact store (S3 or local content-addressed dir)
- Verifier: `scripts/verify_snapshot.py <task_id>` checks downloaded snapshot matches recorded sha256

### 2. Docker per task
- `Dockerfile.template` parameterized per repo
- Builds image tagged `tokenbench/<task_id>:<dataset_version>`
- Image is what the provider runs against — repo state inside the image is byte-identical across machines
- Image digest stored in `task.repo.docker_image`

### 3. Runner upgrade — seeded · idempotent · resumable · parallel
- **Seeded:** every cell takes a seed; same seed → same cell record (or cache hit)
- **Idempotent:** re-running a cell that already succeeded is a no-op (skip + log)
- **Resumable:** checkpoint after each cell; a crashed sweep resumes from the last checkpoint, not from scratch
- **Parallel:** cells run concurrently with bounded concurrency (HAL ran 21,730 rollouts — design for that scale)

### 4. Immutable Results Store (§5 #4)
- Append-only log of run records (versioned by `(dataset_version, harness_version, provider_version, model)`)
- Storage: SQLite for local + Parquet/JSONL exports for sharing
- Query API: `results.query(provider=..., model=..., dataset_version=...)` — used by leaderboard regen

### 5. Reproducibility package
- `repro/` directory containing: pinned `requirements.txt` (or `pyproject.toml` with locked deps), `make repro TASK=<id>` target that pulls snapshot + builds Docker + runs cell
- README with the exact commands a stranger types

## Exit gates
1. **Stranger test:** a teammate clones the repo from scratch, follows `repro/README.md`, and reproduces a known result. Token counts match within ~1%.
2. Killing the runner mid-sweep and resuming produces the same final results store as a clean run.
3. Two parallel runs against the same dataset version produce identical run records (modulo timestamps and run_ids).
4. Snapshot verifier rejects tampered tarballs.

## What this chunk buys
Audit trail. From here on, the leaderboard is regenerable from the results store at any time.
