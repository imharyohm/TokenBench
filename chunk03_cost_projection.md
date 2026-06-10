# Chunk 3 — Cost Projection

Per CHUNK_03 spec §4 ("Cumulative cost ceiling"): project `tasks × providers × models × repeats × per-cell tokens` BEFORE the full sweep. If projected > phase budget, cut breadth (fewer models) before depth (fewer repeats).

## Inputs

**Per-call averages from `python -m tokenbench.usage.report` (2026-06-09 ledger, BM25 sweep, 6 real calls):**
- 7,795 input tokens / 6 calls ≈ **1,300 input tokens / cell**
- 34 output tokens / 6 calls ≈ **5.7 output tokens / cell**

These are the BM25 RAG numbers; each new provider's per-call input differs by how much context it packs into the prompt.

**Sweep dimensions (planned):**
- tasks: 12 (4 per repo × 3 repos: click, rich, httpx)
- providers: 5 (raw_dump, rag-bm25, repo_map, graphify, llmlingua)
- models: 2 (`bedrock.anthropic.claude-sonnet-4-5`, `openai.gpt-4o-mini`)
- repeats: 2

→ **cells = 12 × 5 × 2 × 2 = 240**

## Per-cell estimates (norm tokens)

Build tokens are amortized; per-call (input/output) is what gets sent to the gateway each cell.

| Provider | input / cell | output / cell | build tokens (one-shot) |
|---|---:|---:|---:|
| raw_dump (truncated to 80k budget) | 80,000 | 20 | 0 |
| rag-bm25 (from ledger) | 1,300 | 10 | ~3,000 (BM25 index, local, no LLM) |
| repo_map (Aider default ~8k) | 8,000 | 10 | ~5,000 (tree-sitter parse, local) |
| graphify (god-node traversal output) | 3,000 | 10 | ~50,000 / repo × 3 repos = 150,000 (LLM build, one-shot) |
| llmlingua (BM25 @ 0.5 ratio) | 700 | 10 | 0 (compressor model loaded locally) |

Note: only the graphify build phase consumes gateway tokens. Repo-map and BM25 builds are local CPU work; their `build_tokens_norm` is the count of source tokens read, but no LLM call is made.

## Projected gateway spend

**Per-cell totals across 240 cells:**

| Provider | cells | total input | total output |
|---|---:|---:|---:|
| raw_dump | 48 | 3,840,000 | 960 |
| rag-bm25 | 48 | 62,400 | 480 |
| repo_map | 48 | 384,000 | 480 |
| graphify | 48 | 144,000 | 480 |
| llmlingua | 48 | 33,600 | 480 |
| **TOTAL (per-call)** | **240** | **4,464,000** | **2,880** |

Plus graphify build: 150,000 input + ~5,000 output (one-shot, run on sonnet-4-5).

**Cost (gateway pricing, approximate):**

Half the cells run on sonnet-4-5 (~$3/MTok in, $15/MTok out), half on gpt-4o-mini (~$0.15/MTok in, $0.60/MTok out).

- sonnet-4-5 cells: 2.23M in × $3 + 1.4k out × $15 ≈ **$6.70**
- gpt-4o-mini cells: 2.23M in × $0.15 + 1.4k out × $0.60 ≈ **$0.34**
- graphify build (sonnet-4-5): 150k × $3 + 5k × $15 ≈ **$0.53**
- **TOTAL ≈ $7.57**

## Sensitivity

Dominant term is `raw_dump × sonnet-4-5` (1.92M input tokens ≈ $5.76 — 76% of the bill). If the raw-dump budget is cut from 80k → 40k that drops to ~$2.88 and total to ~$4.70.

## Decision

Projection: **~$7.50.** Total spend so far across all chunks: ~$0.20. No reasonable phase budget is threatened.

**No breadth cuts needed.** Sweep proceeds at full dimensions: 5 providers × 2 models × 2 repeats × 12 tasks.

If gateway pricing surprises us (real cost > 2× projection), the doc-mandated cut order is:
1. Drop gpt-4o-mini → 120 cells, ~$7.20.
2. Drop a repeat → 60 cells, ~$3.60.
3. Reduce raw_dump budget 80k → 40k → halves the dominant term.

## Verification plan (post-sweep)

After the sweep, compare `python -m tokenbench.usage.report 2026-06-10` against this projection. Target: actual within 25% of projected for each model. Larger drift means the per-cell estimates were wrong and the next chunk's projection needs new averages.
