# TokenBench — Context Handoff for Chunk 5

> Paste this whole file (or attach it) into a fresh Claude window when starting Chunk 5. Self-contained — no need to re-read the architecture doc, chunk specs, or transcript unless something is unclear.

---

## What we're building

A **measurement instrument** for codebase-context token efficiency. Runs context methods (RAG, Graphify, repo-map, LLMLingua, raw-dump) through a fixed model on auto-scored tasks, captures normalized token counts, and produces an accuracy-vs-tokens Pareto frontier with build-cost amortization at V ∈ {1, 100, 10000}.

It is **not** a predictor or claim verifier. It's a scale. The user reads the curve and decides which method fits their query volume / accuracy regime.

Reference docs: `tokenbench_architecture.md`, `DECISIONS.md`, `chunks/CHUNK_*.md`, `research/method_fairness_and_model_adapters.md`.

## Status

| Chunk | Status | Headline |
|---|---|---|
| 1 — Skeleton + metric math + locked decisions | DONE | mocks-only, 33 → ... tests over time |
| 2 — Real Anthropic adapter, BM25 RAG, pinned-repo dataset | DONE | rag-bm25 12/12 acc, byte-identical reruns |
| 3 — 5 providers × 2 models × 240-cell sweep | DONE | Pareto + amortization plots, 4 exit gates pass |
| 4 — Reproducibility hardening (snapshot verifier, Docker scaffolding, idempotent/resumable/parallel runner, SQLite mirror, repro/) | DONE | 46 tests, 3/4 exit gates verified by automated test |
| 5 — Free-form QA + judge calibration | NEXT | κ ≥ 0.6 against ≥200-example human gold set |
| 6 — Release | LATER | — |

`dataset_version: 1.0.0`, `harness_version: 0.1.0`. Cumulative gateway spend: ~$7.72.

## Locked decisions (do not relitigate — see `DECISIONS.md`)

1. **Tokenizer:** `o200k_base` via `tiktoken`. Every `*_norm` field uses this encoder.
2. **Public/held-out split:** 80/20, stratified by language and repo size. Held-out kept private.
3. **Isolation boundary:** scoring runs outside the agent container; gold answers never enter the agent's context.
4. **Run records:** append-only, immutable, versioned by `(dataset_version, harness_version, provider_version, model)`.
5. **Build cost amortization:** report TPCA at V ∈ {1, 100, 10000}. A single TPCA without a stated V is forbidden for any method with non-zero build cost.
6. **Method fairness:** **FROZEN PUBLISHED CONFIGS.** No tuning. Switching to equal-budget needs a new `dataset_version`.
7. **Held-out rotation:** 12-month cadence; early-rotate if public-vs-held gap > 2× CI or canary leaks.
8. **Model adapter:** all model providers conform to `tokenbench.models.base.Model` (single chokepoint for native-token capture + o200k re-count + trace).

## Stack

- Python 3.14 in `.venv/` (was 3.11+ minimum). Editable install: `pip install -e ".[dev]"`.
- Pinned deps: `repro/requirements.lock.txt` (103 packages, frozen from live venv at end of Chunk 4).
- Key libs: `pydantic>=2.6`, `tiktoken`, `numpy`, `scipy`, `matplotlib`, `anthropic`, `rank-bm25`, `graphifyy`, `llmlingua`, `tree-sitter`, `pytest`.
- **`aider-chat` cannot install on Py3.14** (`pkgutil.ImpImporter` removed). The repo-map provider is "aider-style on tree-sitter+ast" — documented in `repo_map.py:FROZEN_CONFIG.provenance`.

## Gateway / models

The user's GenAI gateway speaks **Anthropic API format** with model-name prefixes. `.env` at repo root:

```
ANTHROPIC_BASE_URL="https://genai-sharedservice-americas.pwcinternal.com"
ANTHROPIC_AUTH_TOKEN="sk-..."
```

Working model IDs include `bedrock.anthropic.claude-sonnet-4-5`, `bedrock.anthropic.claude-opus-4-7`, `openai.gpt-4o-mini`. The same `AnthropicModel` adapter handles all of them — no per-vendor adapter file is needed. The adapter clamps `max_tokens >= 16` for `openai.*` models (gateway requirement). `tokenbench/core/env.py` loads `.env` once at startup.

`tokenbench/usage/` writes one JSONL row per gateway call to `artifacts/usage/YYYY-MM-DD.jsonl` (response_id-correlated, native input/output, cache, latency). `python -m tokenbench.usage.report` rolls up daily totals. Native-vs-billing drift verified at 0.00%.

## Repo layout

```
Token Efficinecy Benchmark/
├── tokenbench_architecture.md        reference design doc
├── DECISIONS.md                      8 locked decisions
├── power_calc.md                     |T|≥49 floor; planning 100 tasks
├── pyproject.toml / requirements.txt
├── .env                              gateway URL + token (gitignored)
├── .gitignore                        excludes graphify-out/, __pycache__/, …
├── Dockerfile.template               per-repo snapshot container (Chunk 4)
├── run_demo.py                       Chunk 1 mock end-to-end
├── run_chunk2.py / run_chunk3.py     real sweeps
├── chunks/                           6 chunk specs
├── research/method_fairness_and_model_adapters.md
├── repro/                            Chunk 4 stranger-test entrypoint
│   ├── Makefile                      `make repro TASK=<id>`
│   ├── README.md
│   ├── run_cell.py                   single-cell driver, prints RunRecord JSON
│   └── requirements.lock.txt         103 pinned deps
├── scripts/
│   ├── snapshot_repos.py             clone+pin pinned repos
│   ├── verify_snapshot.py            (Chunk 4) re-hash + reject mismatches
│   ├── build_images.py               (Chunk 4) build Docker images, write digests
│   ├── export_parquet.py             (Chunk 4) JSONL → SQLite → Parquet
│   └── build_metrics_math_pdf.py
├── artifacts/
│   ├── repos/{click,rich,httpx}/     pinned snapshots at exact SHAs
│   ├── graphs/{click,rich,httpx}.json   pre-built graphify caches
│   ├── docker/digests.json           (populated when images built)
│   └── usage/YYYY-MM-DD.jsonl        per-call gateway ledger
├── results/
│   ├── runs/chunk2_*.jsonl, chunk3.jsonl(+.db), chunk3_*.png
│   └── findings/CHUNK_03_findings.md
└── tokenbench/
    ├── __init__.py                   HARNESS_VERSION = "0.1.0"
    ├── core/                         env, schemas (frozen pydantic), tokenizer, metrics
    ├── models/                       base.py, mock.py, anthropic.py
    ├── providers/                    base, prompt_wrapper, mock, rag, raw_dump,
    │                                 repo_map, graphify, llmlingua
    ├── datasets/                     base, mock, repo_pins, needle_codebase
    ├── judges/                       base, auto_contains
    ├── runner/engine.py              idempotent · resumable · parallel (Chunk 4)
    ├── results/
    │   ├── store.py                  canonical JSONL append-log, cell_key()
    │   └── sqlite_store.py           queryable SQLite mirror (Chunk 4)
    └── usage/                        per-call gateway ledger
```

`tests/` — 46 passing.

## Key interfaces (don't change without bumping `harness_version`)

```python
# tokenbench/providers/base.py
class Provider(ABC):
    name: str; version: str; config: dict
    def build(self, task) -> BuildArtifact: ...
    def retrieve(self, task, artifact) -> RetrievedContext: ...

@dataclass(frozen=True)
class BuildArtifact:
    payload: object
    build_tokens_norm: int   # one-time cost, amortized via metrics.tpca(V)

@dataclass(frozen=True)
class RetrievedContext:
    text: str                # full prompt — must use prompt_wrapper.standard_prompt
    input_tokens_norm: int

# tokenbench/models/base.py
class Model(ABC):
    name: str; provider: str
    def complete(self, prompt: str, *, max_tokens=1024, seed=0) -> ModelResponse: ...

@dataclass(frozen=True)
class ModelResponse:
    text: str
    native_input_tokens: int; native_output_tokens: int
    norm_input_tokens: int;   norm_output_tokens: int
    latency_ms: int; raw_trace: dict
```

**Standardized prompt wrapper (don't bypass):** every `Provider.retrieve()` builds its prompt via `tokenbench.providers.prompt_wrapper.standard_prompt(context=..., question=...)`. Anti-format-confound: only the CONTEXT changes between providers; wording is fixed.

## Chunk 3 headline numbers (sonnet-4-5; gpt-4o-mini matches except graphify)

| Provider | Acc | TPCA(V=1) | TPCA(V=100) | TPCA(V=10k) |
|---|---:|---:|---:|---:|
| rag-bm25 | 1.000 | 351,172 | 4,585 | 1,120 |
| llmlingua-rag | 1.000 | 350,703 | 4,117 | 651 |
| raw-dump | 1.000 | 80,122 | 80,122 | 80,122 |
| graphify | 1.000 | 628,449 | 7,989 | 1,784 |
| repo-map | 0.667 | 24,088 | 12,258 | 12,140 |

graphify on gpt-4o-mini = 0.917 (the only model-divergent provider; both failures = `needle-rich-0006`). Full findings: `results/findings/CHUNK_03_findings.md`.

**Carry-forward facts:**
- Chunk 2's rag-bm25 numbers reproduced byte-identical inside Chunk 3 — the chain holds.
- repo-map fails 0/8 on `rich` because the frozen 8k budget is too small for a 13k-node graph. Per DECISIONS.md #6, that **is** the score; do not retune.
- graphify build uses **0 gateway tokens** (pure tree-sitter). `build_tokens_norm` reports rendered-deliverable size in o200k, not LLM spend. Amortization curves use this; cost projections should not.

---

## Chunk 4 — what was actually built (read before Chunk 5)

**Three open decisions resolved at entry:**
1. **Docker base image: `python:3.14-slim`.** Matches `.venv`. Preserves all 240 Chunk 3 records.
2. **Results store: SQLite mirror + Parquet exporter script.** SQLite is the queryable source-of-truth; Parquet derived. JSONL stays canonical.
3. **`graphify-out/` cleanup: gitignore + exclude from snapshot hashing.** Patterns in `repo_pins.py:SNAPSHOT_EXCLUDE_DIRS`.

**What was added:**

| File | Purpose |
|---|---|
| `tokenbench/datasets/repo_pins.py` | `SNAPSHOT_EXCLUDE_DIRS` + canonical `hash_tree()`. |
| `scripts/verify_snapshot.py` | Verifier (`all`/`<short_id>`/`<task_id>`). Exit codes: 0 ok, 1 mismatch/missing, 2 unknown id. |
| `Dockerfile.template` + `scripts/build_images.py` | Per-repo snapshot containers; writes `artifacts/docker/digests.json`. |
| `tokenbench/datasets/needle_codebase.py` | Reads `digests.json` (graceful when missing) → `Task.repo.docker_image`. |
| `tokenbench/runner/engine.py` | **REWRITTEN.** Idempotent (cell-key skip via `ResultsStore.completed_keys()`); resumable; parallel via `RunConfig.concurrency` + `ThreadPoolExecutor`; `_BuildCache` memoises `(provider, task)` across repeats. |
| `tokenbench/results/store.py` | Added `cell_key()`, `completed_keys()`, thread-safe append. JSONL still canonical. |
| `tokenbench/results/sqlite_store.py` | `SQLiteStore.from_jsonl(...)`; `.query(provider=, model=, dataset_version=, task_id=)`; `.ingest()` idempotent. |
| `scripts/export_parquet.py` | JSONL → SQLite → Parquet. Graceful "install pyarrow" error if dep missing. |
| `repro/{Makefile,README.md,run_cell.py,requirements.lock.txt}` | `make repro TASK=<id>` is the stranger entrypoint. |
| `.gitignore` | Added `graphify-out/`. |

**Tests added (46 total, was 33):** `test_snapshot.py` (5), `test_runner_chunk4.py` (4), `test_sqlite_store.py` (4).

### Two **important** behaviour changes downstream agents must know

1. **`Runner.sweep()` now skips already-recorded cells.** The returned list contains *only newly-executed* cells, NOT the full set. `run_chunk3.py` was patched to read `store.all()` filtered by the sweep's selection. **Any new sweep driver (e.g. `run_chunk5.py`) must do the same**, or summary tables print empty after a resumed run.
2. **`provider.build(task)` is called once per `(provider, task)` per sweep.** If a provider has side-effects in `build()` you depended on running per-cell, that's gone. None of the current providers do.

### Chunk 4 exit gates — current status

| Gate | Status | Evidence |
|---|---|---|
| 1. Stranger test reproduces a known result within ~1% | **Wired, not yet run from a clean clone.** `repro/run_cell.py --task needle-click-0000` works inside the live env (acc=1.0, input_tokens_norm=1127). | Headline manual test for Chunk 5 entry. |
| 2. Kill+resume = clean run | **PASS** | `tests/test_runner_chunk4.py::test_resume_after_partial_run_matches_clean_run` |
| 3. Parallel ≡ sequential cell-keys + telemetry | **PASS** | `tests/test_runner_chunk4.py::test_parallel_run_produces_same_cell_keys_as_sequential` |
| 4. Snapshot verifier rejects tampered tarballs | **PASS** | `tests/test_snapshot.py::test_verifier_rejects_tampered_snapshot` |

### Deferred from Chunk 4

1. **Docker images not actually built** — daemon was offline. All scaffolding tested at code level. To finalise: start Docker Desktop, run `python scripts/build_images.py`. Populates `artifacts/docker/digests.json` and `Task.repo.docker_image`.
2. **`pyarrow` not installed.** `scripts/export_parquet.py` fails gracefully with install hint. `pip install pyarrow` if Parquet needed.
3. **Stranger test from a clean clone.** Recommended: a second machine (or fresh user account on this Mac) with the gateway token in `.env`, then `cd repro && make repro TASK=needle-click-0000`.

---

## Chunk 5 plan (what to build next)

Read `chunks/CHUNK_05_judge.md` for the full spec. Job: extend beyond auto-scored needles into free-form QA, with a **calibrated** LLM judge.

**Deliverables:**
1. `datasets/swe_qa.py` — SWE-QA loader (free-form questions; same `Task` schema; `scoring: "llm_judge"`).
2. `judges/llm_judge.py` — separated judge model (≠ answering model, anti-self-preference); multi-dim rubric (correctness/completeness/faithfulness); N-way majority vote (N ≥ 3); anonymized + shuffled inputs.
3. **≥200-example human gold set** with annotator id + timestamp. (30 too few for stable κ.)
4. `scripts/calibrate_judge.py` — Cohen's κ + ECE. **Pass condition: κ ≥ 0.6** (pre-registered). On fail: SWE-QA stays exploratory; headline numbers stay on auto-scored datasets.
5. Judge run records — full prompt+response stored to `trace_uri`; per-dimension scores alongside binary pass/fail.

**Exit gates:** see `chunks/CHUNK_05_judge.md` lines 42–46.

**Practical notes for the next agent:**

1. **κ ≥ 0.6 is pre-registered.** Do **not** relabel human gold after seeing judge outputs — that's p-hacking. Architecture doc §5 #4 and CHUNK_05.md both call this out. Verified by `git log` on the gold set.
2. **Judge model ≠ answering model.** If sonnet-4-5 produces an answer, judge runs on a different model id (e.g. opus-4-7 or gpt-4o). The current `AnthropicModel` adapter handles all gateway-prefixed models; this is a config choice.
3. **SWE-QA gold set source.** Decide with user: hand-curate from `artifacts/repos/{click,rich,httpx}/` (cheap, hours), or pull a public benchmark like SWE-bench/RepoQA-style (faster but contamination risk).
4. **Don't break Chunk 3 numbers.** Spot-check: `python run_chunk3.py --tasks-per-repo 1 --repeats 1 --providers rag-bm25 --models bedrock.anthropic.claude-sonnet-4-5`. ~$0.0001 now thanks to idempotent skip.
5. **Read Chunk 4's "two important behaviour changes" above before writing any sweep driver.**
6. **The user prefers concise updates, no narration.** Tool calls speak for themselves; one-sentence text between groups; end-of-turn summary in two sentences max.
7. **The user wants to be in the loop on big choices.** Specifically for Chunk 5: judge model selection, SWE-QA source, ECE threshold to write into DECISIONS.md, how the ≥200 human gold labels get produced (you cannot synthesise them).
8. **Cross-chunk diagnostic:** graphify on gpt-4o-mini drops 2/24 on `needle-rich-0006`. With a calibrated judge over free-form answers, the model-divergence story may extend or contract — keep that task ID in mind.

## Resume checklist

```bash
cd "/Users/hgupta163/dev/Token Efficinecy Benchmark"
source .venv/bin/activate
pytest -q                              # 46 passing (or 45 + 1 skipped if no creds)
python scripts/verify_snapshot.py      # all 3 snapshots ok
ls results/runs/chunk3.jsonl           # 240+ records
ls artifacts/graphs/                   # click.json, rich.json, httpx.json
ls artifacts/docker/digests.json 2>/dev/null || echo "(images not built yet — fine for Chunk 5)"
ls repro/                              # Makefile, README.md, run_cell.py, requirements.lock.txt
```

Then:
1. Read `chunks/CHUNK_05_judge.md`.
2. Read this file (you already are) and `results/findings/CHUNK_03_findings.md`.
3. Confirm with user: judge model, SWE-QA source, gold-set production plan, ECE threshold.
4. Build deliverables 1→5 in spec order; run `pytest -q` after each.
5. Run Chunk 5 exit gates. The κ ≥ 0.6 calibration result is the headline.

---

**Status as of Chunk 4 handoff:** Chunks 1–4 complete. 46/46 tests green. `dataset_version: 1.0.0`, `harness_version: 0.1.0`. Cumulative gateway spend: ~$7.72. Three of four Chunk 4 exit gates verified by automated test; the stranger-from-clean-clone is wired but unrun (acceptable for Chunk 5 entry). Ready for Chunk 5.
