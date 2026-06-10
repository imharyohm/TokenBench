# Chunk 6 — Realism + Rigor + Release (P6)

> Maps to: §3 P6, §1[10][11], §2 (contamination + harness gaming rows), §6 (definition of done)

## Goal
Take the benchmark from "works on clean QA" to "publishable instrument." Adds the agentic provider, contamination defenses, exploit detection, and the release surface.

## Entry gate
Chunk 5 passed: judge is calibrated (or SWE-QA is flagged exploratory).

## Deliverables

### 1. `providers/swe_bench_pro.py` — agentic provider (telemetry only)
- Wraps SWE-bench Pro agent loop
- We do NOT score the agent's correctness here — we measure its **token consumption** as a context method
- Full trace captured per attempt: every tool call, every file read
- Tasks scored with the existing scorers (auto / unit-test / judge)

### 2. Iso-accuracy and iso-budget sweeps
- **Iso-accuracy:** for a fixed accuracy target (e.g. 70%), report tokens spent per method
- **Iso-budget:** for a fixed token budget (e.g. 50k tokens/query), report accuracy reached per method
- Both reported alongside the headline TPCA(V) curve

### 3. Statistical rigor
- ≥5 repeats per cell (per P6 spec)
- Bootstrap CIs over tasks AND repeats
- Task count fixed by the **P0 power calc** from Chunk 1 — verify the count was met
- Median + IQR reported, not mean (token usage is heavy-tailed)

### 4. Held-out split + rotation policy (§5 #7)
- **Public split:** anyone can run, leaderboard accepts submissions
- **Held-out split:** kept private, used to detect contamination
- **Rotation policy** (locked in DECISIONS.md from Chunk 1):
  - Cadence (e.g. every 6 months, or when contamination is detected)
  - Trigger for early rotation (gap between public and held-out exceeds threshold)
  - What happens to past leaderboard entries on rotation (archived with a `dataset_version` tag)
- **Public-vs-held-out gap check:** if gap exceeds noise band, flag the suspected method/model as contaminated

### 5. Trace-aware exploit detector
The doc cites UC Berkeley RDI: 8 major agent benchmarks driven to ~100% by gaming the harness. Defense:
- For each run record, scan the trace for tool calls that touched **gold-answer files outside the provider's returned context**
- Flag any such run as "harness exploit suspected"
- **Audit the top-N submissions before publishing** them on the leaderboard

### 6. Datasheet (Datasheets for Datasets, Gebru et al.)
- Finalized from the P0 draft (Chunk 1)
- Provenance, licensing, intended use, out-of-scope use, known limitations
- Required for any public release

### 7. Public leaderboard + submission protocol
- Web UI (or simple Markdown table regenerated from results store)
- Submission protocol: submitter sends a Provider plugin + config; we run it on both splits; gap is reported
- Two columns: TPCA(V=1), TPCA(V=10000) so cold-start vs amortized is visible

### 8. Trivial baselines for sanity
- **Trivial baseline:** zero-context (model answers from priors only). If a method doesn't beat this, it's worse than nothing.
- **Exploit baseline:** an agent that intentionally tries to game the harness. Should score ~0 if defenses work.

## Exit gates (all must pass — these define "done" per §6)
1. Public-vs-held-out gap within noise (no contamination signal across submitted methods).
2. Exploit baseline scores ~0.
3. Trace audit shows no harness gaming on the top-N submissions.
4. Results stable across ≥5 repeats within the pre-computed CI width.
5. A stranger can: clone the repo, `pip install`, pull a pinned task environment, run any (provider × model) cell, get token + accuracy numbers that match published CIs, and see *why* via the trace.
6. Leaderboard shows accuracy-vs-normalized-token Pareto frontier across methods, not a single "Nx" claim.

## What "done" looks like (§6)
> "You're not claiming '71.5×' — you're publishing the curve that tells anyone which method is genuinely efficient for their query volume and accuracy bar."
