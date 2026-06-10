# TokenBench — Chunk Index

Six chunks, each maps to one phase from `tokenbench_architecture.md` §3. Each chunk has an entry gate, deliverables, and an exit gate that must pass before moving on.

```
Chunk 1 ─► Chunk 2 ─► Chunk 3 ─► Chunk 4 ─► Chunk 5 ─► Chunk 6
skeleton    signal     coverage   reproduce  judge      release
(validity)             (reliability)         (governance)
```

| # | File | Phase | Goal | Real LLM calls? |
|---|------|-------|------|-----------------|
| 1 | [CHUNK_01_skeleton.md](CHUNK_01_skeleton.md) | P0/P1 | Scaffold, schemas, metric math, locked decisions | ❌ mocks only |
| 2 | [CHUNK_02_first_signal.md](CHUNK_02_first_signal.md) | P2 | RepoQA + RAG + Anthropic adapter | ✅ first real numbers |
| 3 | [CHUNK_03_provider_expansion.md](CHUNK_03_provider_expansion.md) | P3 | Graphify, repo-map, LLMLingua, raw-dump | ✅ Pareto frontier emerges |
| 4 | [CHUNK_04_reproducibility.md](CHUNK_04_reproducibility.md) | P4 | Pinned snapshots, Docker, resumable runner | ✅ stranger-reproducible |
| 5 | [CHUNK_05_judge.md](CHUNK_05_judge.md) | P5 | SWE-QA + LLM-judge calibration (κ ≥ 0.6) | ✅ free-form QA online |
| 6 | [CHUNK_06_release.md](CHUNK_06_release.md) | P6 | Agentic provider, exploit detector, leaderboard | ✅ public release |

## Why this ordering

From the architecture doc (§3):
> The ordering is deliberate: **cleanest controlled measurement first** (single-shot QA + automatic scoring), expanding outward to messier-but-more-realistic settings (free-form QA, then agentic), trusting each new layer only after its gate passes.

## What's locked in Chunk 1 and never re-litigated

These are the §5 decisions — expensive to retrofit:
1. Reference tokenizer (`o200k_base`)
2. Public/held-out split policy
3. Isolation boundary (scorer outside agent container; gold never in-context)
4. Immutable, versioned run records
5. Build-cost amortization (TPCA at V ∈ {1, 100, 10000})
6. Method-fairness protocol (frozen vs equal-budget tuning)
7. Held-out rotation cadence

## How to use these chunks

1. Open the chunk you're starting.
2. Verify its **entry gate** is satisfied (previous chunk's exit gate passed).
3. Build the deliverables.
4. Run the **exit gate** checks. If any fail, fix before moving on — do not roll forward with broken foundations. The whole point of the gating is that confounds caught late are 10× more expensive than confounds caught early.

## Parallelization note

Within a chunk, sub-tasks may be independent (Chunk 1 lists explicit fan-out points: A/B/C/D). Across chunks, work is **mostly sequential** — Chunk 2 needs Chunk 1's interfaces, Chunk 4 needs Chunk 3's providers. The exception: Chunks 5 (judge) and 4 (Docker) can overlap if you have the bandwidth, since the judge work doesn't depend on Docker.
