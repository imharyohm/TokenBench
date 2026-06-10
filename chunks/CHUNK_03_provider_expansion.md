# Chunk 3 — Provider Expansion (P3)

> Maps to: §3 P3, §1[3], §2 (tuning-effort confound), §5 #5 + #6

## Goal
Add the rest of the context methods behind the same Provider interface. Build cost tracked + amortized at all three V values. Method-fairness protocol enforced.

## Entry gate
Chunk 2 passed: one provider produces real, reproducible numbers.

## Deliverables

### 1. New providers (each behind `providers/base.py`)
- `providers/raw_dump.py` — naive baseline: dump full repo (or as much as fits) into context. Useful as floor.
- `providers/graphify.py` — knowledge-graph build, query via god nodes / community detection
- `providers/repo_map.py` — Aider's repo-map (tree-sitter symbols, ranked by graph centrality)
- `providers/llmlingua.py` — LLMLingua-2 prompt compression on top of one of the above

Each provider:
- Reports `build_tokens_norm` separately from per-query `input_tokens_norm`
- Uses the **same standardized prompt wrapper** as Chunk 2
- Has a frozen config (no per-task tuning during the scoring run)

### 2. Build-cost amortization (§5 #5)
- `metrics.py` already supports TPCA(V) from Chunk 1
- Run the full sweep, plot TPCA at V ∈ {1, 100, 10000}
- Plot the **amortization curve** (TPCA vs V on log-x) per method — this is where Graphify's story lives or dies

### 3. Method-fairness protocol (§5 #6)
Pick ONE in P0/Chunk 1 and apply here:
- **Option A (frozen):** every provider uses its published default config; no tuning allowed
- **Option B (equal budget):** every provider gets N hours / M tokens of tuning on a **dev split only**; configs frozen before scoring
- Tuning logs archived in the run records

### 4. Cumulative cost ceiling
- Before kicking off the full sweep: project tasks × providers × models × repeats × per-cell token cost
- If projected > phase budget: **cut breadth (fewer models) before depth (fewer repeats)**
- Document the projection in `chunk03_cost_projection.md`

## Exit gates
1. Swapping provider changes only token/accuracy; task and model are byte-identical across runs.
2. Amortization curve plotted at V ∈ {1, 100, 10000} for every method.
3. Tuning logs archived alongside run records (or "frozen configs" declared with no tuning).
4. Cost projection done; sweep stays within phase budget.

## What this chunk reveals
The Pareto frontier across methods. The headline visual of the whole benchmark.
