# TokenBench v1.0.0

A rigorous token-efficiency benchmark for codebase-context retrieval methods — measuring accuracy vs. tokens on the Pareto frontier with build-cost amortization across configurable query volumes.

`dataset_version: 1.0.0` · `harness_version: 0.1.0` · `JUDGE_RUBRIC_VERSION: 1.1.0`

---

## Why TokenBench

Public claims of "Nx token efficiency" routinely conflate cold-start cost with amortized cost, ignore the priors floor, and use scoring that can be gamed. TokenBench exists to fix that. It is a **measurement instrument**, not a leaderboard claim: every result is an (accuracy, tokens) point on a curve indexed by query volume V. The right method depends on your regime — read the curve, don't trust a single number.

The primary metric is **TPCA(V)** — Tokens Per Correct Answer at amortization volume V:

```
TPCA(m, V) = Σ tokens(m, t, r, V)  /  Σ 1{correct(m, t, r)}

where tokens(m, t, r, V) = input_norm + output_norm + (build_norm / V)
```

A single TPCA number without a stated V is meaningless for methods with non-zero build cost (RAG indexes, Graphify). The leaderboard always reports both `TPCA(V=1)` (cold start) and `TPCA(V=10000)` (amortized).

---

## What's measured

**Two task families, three pinned Python repos:**

| Family | Tasks | Public | Held-out | Scoring |
|---|---:|---:|---:|---|
| needle-codebase | 300 | 240 | 60 | `AutoContainsJudge` (exact substring) |
| swe-qa | 210 | 168 | 42 | `LLMJudge` (Claude Opus, N=3, rubric v1.1.0) |

**Pinned repos** (content-addressed by `sha256`):

| Repo | Commit | License |
|---|---|---|
| [click](https://github.com/pallets/click) | `8a1b1a33` | BSD-3-Clause |
| [rich](https://github.com/Textualize/rich) | `46cebbb0` | MIT |
| [httpx](https://github.com/encode/httpx) | `b5addb64` | BSD-3-Clause |

needle-codebase auto-generates tasks by AST-parsing each repo for functions with docstrings ≥ 30 characters. swe-qa contains 210 hand-curated free-form questions with reference answers.

---

## Methods (providers)

| Provider | Description |
|---|---|
| `rag-bm25` | BM25 index over chunked source files; top-k retrieved at query time |
| `repo-map` | Aider-style compact symbol map of the repo structure |
| `graphify` | Call-graph + import-graph context extraction |
| `llmlingua-rag` | BM25 retrieval + LLMLingua prompt compression |
| `raw-dump` | Entire repo source concatenated into the prompt (baseline) |
| `zero-context` | No context — priors floor baseline |
| `exploit-baseline` | Output-side priming canary; used to audit scorer leniency |

---

## Leaderboard (public split)

### needle

| ★ | Provider | Model | Acc | TPCA(V=1) | TPCA(V=10k) |
|---|---|---|---:|---:|---:|
| ★ | repo-map | claude-sonnet-4-5 | 1.000 | 16,023 | 8,055 |
| ★ | repo-map | gpt-4o-mini | 1.000 | 16,023 | 8,055 |
|   | rag-bm25 | claude-sonnet-4-5 | 1.000 | 257,824 | 1,145 |
|   | rag-bm25 | gpt-4o-mini | 1.000 | 257,824 | 1,145 |
|   | graphify | claude-sonnet-4-5 | 1.000 | 112,934 | 1,537 |
|   | raw-dump | gpt-4o-mini | 1.000 | 80,086 | 80,086 |
|   | graphify | gpt-4o-mini | 0.950 | 118,878 | 1,618 |
|   | llmlingua-rag | claude-sonnet-4-5 | 0.875 | 294,061 | 713 |
|   | llmlingua-rag | gpt-4o-mini | 0.700 | 367,576 | 891 |

### swe_qa

| ★ | Provider | Model | Acc | TPCA(V=1) | TPCA(V=10k) |
|---|---|---|---:|---:|---:|
| ★ | rag-bm25 | claude-sonnet-4-5 | 0.688 | 543,179 | 1,962 |
| ★ | repo-map | claude-sonnet-4-5 | 0.376 | 43,166 | 21,983 |
|   | llmlingua-rag | claude-sonnet-4-5 | 0.472 | 790,724 | 1,832 |
|   | graphify | claude-sonnet-4-5 | 0.352 | 2,079,564 | 6,883 |
|   | rag-bm25 | gpt-4o-mini | 0.312 | 1,197,249 | 3,797 |
|   | llmlingua-rag | gpt-4o-mini | 0.128 | 2,914,701 | 5,663 |
|   | repo-map | gpt-4o-mini | 0.112 | 143,300 | 72,186 |
|   | graphify | gpt-4o-mini | 0.064 | 11,435,380 | 35,636 |

★ = Pareto frontier (accuracy vs tokens at V=1). Full table with 95% CIs and median token counts: [LEADERBOARD.md](LEADERBOARD.md).

---

## Quickstart

**Requirements:** Python ≥ 3.11, API keys for your chosen model provider.

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Set credentials
cp .env.example .env   # then fill in your keys

# 3. Snapshot the pinned repos (one-time, verifies sha256)
python scripts/snapshot_repos.py

# 4. Dry-run to see projected cost before spending
python run_chunk6_rigor.py --dry-run

# 5. Run the full rigor sweep (3 repeats per cell, public split)
python run_chunk6_rigor.py

# 6. Regenerate the leaderboard
python scripts/generate_leaderboard.py

# 7. Open the visual leaderboard
open leaderboard.html
```

---

## Repository structure

```
tokenbench/
  core/          # schemas, tokenizer, cell-key deduplication
  datasets/      # needle-codebase AST generator, swe-qa loader
  providers/     # rag, repo-map, graphify, llmlingua, raw-dump, baselines
  judges/        # AutoContainsJudge, LLMJudge (rubric v1.1.0)
  models/        # model adapters (Anthropic, OpenAI)
  runner/        # harness loop, idempotent run-record store
  audit/         # exploit-detector checks (C1–C4)
  results/       # run records (gitignored except manifests)

artifacts/
  needle/v1.0.0/public_split.tsv
  swe_qa/v1.0.0/public_split.tsv
  swe_qa/v1.0.0/human_labels.jsonl
  _heldout/      # gitignored — never distributed

scripts/
  snapshot_repos.py       # clone + verify pinned repos
  freeze_splits.py        # generate public/held-out manifests
  audit_runs.py           # exploit-detector (gates publication)
  generate_leaderboard.py # regenerate LEADERBOARD.md + leaderboard.html
  calibrate_judge.py      # LLM-judge vs human κ calibration
  sample_swe_qa.py        # stratified subsample for rigor sweep

run_chunk6_rigor.py       # main sweep entrypoint
run_iso.py                # iso-accuracy / iso-budget analysis
```

---

## Submitting a new method

Implement the `Provider` interface and submit a PR:

```python
from tokenbench.providers.base import Provider

class MyProvider(Provider):
    name = "my-method"
    version = "0.1.0"
    config = {"k": 5}           # frozen at submission

    def build(self, task) -> BuildArtifact:
        # one-shot index build; returns artifact + build_tokens_norm
        ...

    def retrieve(self, task, artifact) -> RetrievedContext:
        # per-query retrieval; returns prompt text + input_tokens_norm
        # NEVER read task.gold or task.needle
        ...
```

Three hard rules enforced by the audit gate:
1. **Never read `task.gold` or `task.needle`.** Violations are flagged HIGH and block publication.
2. **Token counts use `o200k_base`** via `tokenbench.core.tokenizer.count_tokens`.
3. **`config` is frozen at submission.** Tuning in response to leaderboard results requires a new `version`.

Full protocol: [SUBMISSION.md](SUBMISSION.md).

---

## Design decisions & reproducibility

- [DECISIONS.md](DECISIONS.md) — every non-obvious design choice (split strategy, idempotency, judge rubric versioning, contamination guards)
- [DATASHEET.md](DATASHEET.md) — dataset card following Gebru et al. 2018
- `repro/requirements.lock.txt` — 103 packages pinned for full reproducibility
- Each run record carries `(task_id, provider_name, provider_version, model, repeat, seed, dataset_version, harness_version)` as a cell key; re-running the same cell is a no-op

---

## Known limitations

- **Priors floor:** zero-context (no retrieval) reaches acc ≈ 0.26 on needle/claude-sonnet-4-5 because the model has seen click/rich/httpx in pretraining. Meaningful headline number is uplift over the priors floor, not raw accuracy.
- **`auto_contains` leniency:** short symbol names (e.g. `meta`) can match any prose containing that word. The `ExploitBaselineProvider` achieves +0.21 paired uplift over zero-context purely from output-side priming without any gold access.
- **Single annotator:** swe-qa labels were authored by one annotator; inter-annotator agreement was not measured. Judge-vs-human κ = 0.806.
- **Static context only:** v1.0 measures static context methods. Agentic providers (model-driven file reads via tool loop) are deferred to v1.1.

---

## License

Benchmark harness and task schemas: MIT.  
Pinned repo content inherits the upstream license of each repo (BSD-3-Clause for click and httpx, MIT for rich).
