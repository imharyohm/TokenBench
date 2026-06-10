# Chunk 3 — Findings

Run: `results/runs/chunk3.jsonl` · 240 cells · 12 tasks × 5 providers × 2 models × 2 repeats · dataset_version 1.0.0 · harness_version 0.1.0.

---

## Headline numbers

| Provider | Model | Accuracy | Avg in+out / cell | Build tokens (one-shot) |
|---|---|---:|---:|---:|
| rag-bm25 | sonnet-4-5 | 24/24 (1.000) | 1,084 | 350,088 |
| rag-bm25 | gpt-4o-mini | 24/24 (1.000) | 1,084 | 350,088 |
| llmlingua-rag | sonnet-4-5 | 24/24 (1.000) | 616 | 350,088 |
| llmlingua-rag | gpt-4o-mini | 24/24 (1.000) | 616 | 350,088 |
| raw-dump | sonnet-4-5 | 24/24 (1.000) | 80,122 | 0 |
| raw-dump | gpt-4o-mini | 24/24 (1.000) | 80,084 | 0 |
| graphify | sonnet-4-5 | 24/24 (1.000) | 1,721 | 626,727 |
| **graphify** | **gpt-4o-mini** | **22/24 (0.917)** | 1,722 | 626,727 |
| **repo-map** | **sonnet-4-5** | **16/24 (0.667)** | 8,093 | 7,966 |
| **repo-map** | **gpt-4o-mini** | **16/24 (0.667)** | 8,051 | 7,966 |

Plots: `results/runs/chunk3_pareto.png`, `results/runs/chunk3_amortization.png`.

---

## Finding 1 — Graphify is the only method whose accuracy depends on the model

- **What:** graphify scored 24/24 on sonnet-4-5 and 22/24 on gpt-4o-mini. Both failures were the same task (`needle-rich-0006`), reproduced across both repeats.
- **Why:** graphify renders nodes as a flat list of `(label, file:line)` pairs, optimised for token economy. The relevant docstring (`"Do something impossible every day."` at `examples/exception.py:L19`) and the function it describes (`divide_all()` at `examples/exception.py:L18`) appear **8 lines apart** in the rendered context, connected only by adjacent file/line metadata.
- sonnet-4-5 makes the cross-reference and answers `divide_all`. gpt-4o-mini ignores the metadata and **fabricates** a function name from the docstring text: `do_something_impossible_every_day`.
- All other providers (BM25, LLMLingua-on-BM25, repo-map, raw-dump) keep docstring and signature **syntactically adjacent** in the source, so the model never has to reconstruct the relationship.
- **Implication:** graphify's per-query format is reasoning-dense — fewer tokens, more reasoning per token. That is the trade-off the benchmark exists to surface, not a bug.

## Finding 2 — repo-map fails on `rich`, perfectly, on both models

- **What:** repo-map scored 16/24 = 0.667 on both models. The failures are identical: `needle-rich-0004`, `-0005`, `-0006`, `-0007` (4/4 rich tasks fail on both repeats × both models = 8 cells per model). click and httpx: 8/8 each.
- **Why:** the 8,000-token aider-style budget is too small for `rich`. The repo has 13,463 graph nodes vs ~2,200 for click/httpx — six times denser. Once the symbol map is sized to budget, the relevant `rich` symbols get ranked off the bottom (PageRank prefers high-centrality core modules, but the needles are scattered across `rich/console.py`, `rich/text.py`, etc.).
- **Implication:** the failure is **frozen-config-correct** — DECISIONS.md #6 mandates published defaults. A larger budget would lift accuracy but would invalidate the comparison. Per the benchmark's own rules: this is the score; record it, move on.

## Finding 3 — the 100% accuracy ceiling is broken

- Chunk 2 had only one provider (rag-bm25) hitting 12/12 — no spread, no Pareto.
- Chunk 3 produces **three distinct accuracy levels**: 1.000, 0.917, 0.667. Every accuracy-vs-token plot in the benchmark from here onward has real shape.

## Finding 4 — model-invariant providers vs model-sensitive providers

- **Model-invariant** (acc identical across both models): rag-bm25, llmlingua-rag, raw-dump.
  These pack enough surface (full source chunks or full source dump) that even a cheap model can lift the answer.
- **Model-sensitive**: graphify (graph reasoning required), repo-map (reasoning over signatures only — though here the failure is budget-bound, not model-bound).
- This is a useful signal: providers that compress harder ship more risk to the model. Cheap models cost you more accuracy than expensive contexts.

## Finding 5 — amortization curves cross exactly where the spec says they will

- **V=1 (cold start):** raw-dump cheapest (0 build cost). graphify worst (~628k build / 1 correct).
- **V≈8:** graphify crosses raw-dump.
- **V≈30–60:** graphify and raw-dump cross repo-map.
- **V→∞:** llmlingua-rag wins (650 TPCA), then rag-bm25 (~1,100), then graphify (~1,800), then repo-map (~12,100), then raw-dump (~80,000).
- Reading the curve at any single V without naming V is a load-bearing lie (DECISIONS.md #5). Confirmed with real data here.

## Finding 6 — graphify build is gateway-free

- The `graphify update --no-cluster` extractor uses tree-sitter only — `input_tokens=0, output_tokens=0` in the produced graph metadata.
- This means the cost-projection ceiling (CHUNK_03 §4) was over-estimated for graphify: my pre-sweep estimate assumed an LLM-driven build at ~50k tokens × 3 repos = 150k. Actual gateway tokens for graphify build = **0**.
- The "build cost" we report is the rendered-deliverable size in o200k tokens (an artefact-equivalent metric), not LLM gateway tokens. This distinction matters for the cost-vs-quality reading: graphify's build is *compute-free* on the gateway side, but still amortizable as a one-time artefact preparation cost.

## Finding 7 — cost projection accuracy

- Projected: 4.46M input tokens, ~$7.57 total.
- Actual: 4.97M input tokens (the day's usage ledger total, including pre-sweep smoke tests and sanity probes).
- Drift: **+11%**, well inside the 25% tolerance the projection doc set for itself.
- The dominant cost term was `raw_dump × sonnet-4-5` (76% of bill, as predicted).

## Finding 8 — Chunk 2 reproduces byte-identical inside Chunk 3

- 12/12 cells of `(rag-bm25, sonnet-4-5, repeat=0)` produced **the exact same `input_tokens_norm`** in `chunk3.jsonl` as in `chunk2_A.jsonl`.
- BM25 is deterministic, the index is fixed, and the prompt wrapper hasn't changed. The chain holds.

---

## Open questions for later chunks

1. Does graphify's reasoning-dense penalty disappear with a structurally richer renderer (e.g. group nodes by source_file, put name + docstring on adjacent lines)? Would require a `harness_version` bump per DECISIONS.md.
2. Would repo-map at a 16k or 32k budget recover the rich failures, and would the cost still be Pareto-optimal? Equal-budget vs frozen-config trade-off (DECISIONS.md #6).
3. Are there tasks where `divide_all`-style fabrication happens *without* a model-name change? i.e. does the dataset have any tasks both models miss in the same way? Check at higher N before scaling.
