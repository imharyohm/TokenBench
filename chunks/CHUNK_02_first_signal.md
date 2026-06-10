# Chunk 2 — First Real Signal (P2)

> Maps to: §3 P2, §1[3][4][6], §2 (tokenizer + format confounds)

## Goal
Get **real** numbers from one method on auto-scored tasks. RepoQA + RAG provider + real model adapter. Zero judge risk (RepoQA is auto-scored: needle-containment).

## Entry gate
Chunk 1 passed: skeleton green, mocks working, decisions locked, power calc done.

## Deliverables

### 1. `datasets/repoqa.py` — real RepoQA loader
- Pulls RepoQA tasks (needle_function type)
- Each task carries: repo @ commit, question, gold needle, canary string
- Snapshots are content-addressed (sha256 of tarball)
- License field populated per source repo
- Tasks emitted as the frozen `Task` schema from Chunk 1

### 2. `providers/rag.py` — first real provider
- Interface: `Provider.build(repo) → BuildArtifact` + `Provider.retrieve(question, artifact) → context_str`
- Implementation: chunk repo files, embed (sentence-transformers or OpenAI embeddings — pick one, document), retrieve top-K chunks
- Build cost (one-time index) tracked separately in telemetry as `build_tokens_norm`
- Per-query cost tracked as `input_tokens_norm` (the retrieved context that goes into the prompt)
- **Standardized prompt wrapper** (system + question template) — same wrapper used by every provider so format isn't a confound

### 3. `models/anthropic.py` — first real model adapter
- Wraps Anthropic SDK
- Pulls **token usage from the provider's usage API** (ground truth) → `native_input`, `native_output`
- Re-counts everything in `o200k_base` → `*_norm` fields
- Captures full trace: every API call, prompt, response → `trace_uri` (local file ok in P2)

### 4. `judges/auto_contains.py` — already exists from Chunk 1
- Just confirm it works on real RepoQA: `correct = (gold_needle in model_output)`

### 5. Reproducibility check
- Run the full sweep twice, independently. Numbers must agree within CI bounds.
- Token counts must match Anthropic billing dashboard to within a few %.

## Exit gates (must all pass)
1. Real numbers from RAG × Anthropic × RepoQA reproduce across two runs within bootstrap CIs.
2. Native token counts match provider billing dashboard within ~3%.
3. Trace files capture every tool call / API call.
4. Build cost is tracked separately from per-query cost.
5. Standardized prompt wrapper is in place — confirmed by reading the wrapper code.

## Out of scope (defer to later chunks)
- Other providers (Chunk 3)
- Other models / multi-model comparison (Chunk 3)
- Free-form QA / LLM-judge (Chunk 5)
- Docker per task (Chunk 4)
- Held-out split (Chunk 6)
