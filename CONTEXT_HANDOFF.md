# TokenBench — Context Handoff for Chunk 6

> Paste this whole file (or attach it) into a fresh Claude window when starting Chunk 6. Self-contained — no need to re-read the architecture doc, chunk specs, or transcript unless something is unclear.

---

## What we're building

A **measurement instrument** for codebase-context token efficiency. Runs context methods (RAG, Graphify, repo-map, LLMLingua, raw-dump) through a fixed model on auto-scored tasks, captures normalized token counts, and produces an accuracy-vs-tokens Pareto frontier with build-cost amortization at V ∈ {1, 100, 10000}.

It is **not** a predictor or claim verifier. It's a scale. The user reads the curve and decides which method fits their query volume / accuracy regime.

Reference docs: `tokenbench_architecture.md`, `DECISIONS.md`, `chunks/CHUNK_*.md`, `research/method_fairness_and_model_adapters.md`.

## Status

| Chunk | Status | Headline |
|---|---|---|
| 1 — Skeleton + metric math + locked decisions | DONE | mocks-only, 33 tests |
| 2 — Real Anthropic adapter, BM25 RAG, pinned-repo dataset | DONE | rag-bm25 12/12 acc, byte-identical reruns |
| 3 — 5 providers × 2 models × 240-cell sweep | DONE | Pareto + amortization plots, 4 exit gates pass |
| 4 — Reproducibility hardening (snapshot verifier, Docker scaffolding, idempotent/resumable/parallel runner, SQLite mirror, repro/) | DONE | 46 tests, 3/4 exit gates verified by automated test |
| 5 — Free-form QA + judge calibration | **DONE** | 210 human labels @ commit `d95de96`; judge calibrated under rubric v1.1.0 (κ=0.806, ECE=0.092); SWE-QA headline-eligible |
| 6 — Release | NEXT | Trivial baselines, iso-acc/iso-budget, 5-repeat rigor pass (incl. SWE-QA), exploit detector, held-out split, datasheet, local leaderboard. Agentic provider deferred to v1.1. |

`dataset_version: 1.0.0`, `harness_version: 0.1.0`, `JUDGE_RUBRIC_VERSION: 1.1.0`. Cumulative gateway spend: **~$15** (Chunks 2–3 ~$7.72 + Chunk 5 candidate generation ~$2 + Chunk 5 judge run ~$5).

**Repo is local git only** (initialized 2026-06-10, no remote). Pre-registration boundary `7438ee7` (labels not yet authored) → labels committed at `d95de96` (Chunk 5 deliverable 3) — `git log` shows labels strictly after pre-reg, satisfying Chunk 5 exit gate 4. **User plans to push to GitHub later from a second device** (not at v1.0).

## Locked decisions (do not relitigate — see `DECISIONS.md`)

1. **Tokenizer:** `o200k_base` via `tiktoken`. Every `*_norm` field uses this encoder.
2. **Public/held-out split:** 80/20, stratified by language and repo size. Held-out kept private. **(Not yet executed; planned for Chunk 6 deliverable E.)**
3. **Isolation boundary:** scoring runs outside the agent container; gold answers never enter the agent's context.
4. **Run records:** append-only, immutable, versioned by `(dataset_version, harness_version, provider_version, model)`.
5. **Build cost amortization:** report TPCA at V ∈ {1, 100, 10000}. A single TPCA without a stated V is forbidden for any method with non-zero build cost.
6. **Method fairness:** **FROZEN PUBLISHED CONFIGS.** No tuning. Switching to equal-budget needs a new `dataset_version`.
7. **Held-out rotation:** 12-month cadence; early-rotate if public-vs-held gap > 2× CI or canary leaks.
8. **Model adapter:** all model providers conform to `tokenbench.models.base.Model` (single chokepoint for native-token capture + o200k re-count + trace).
9. **Judge model:** `bedrock.anthropic.claude-opus-4-7`. Must differ from any answering model. Within-family bias risk mitigated by anonymized inputs + 20-task `openai.gpt-4o` robustness check.
10. **SWE-QA source:** hand-curated against pinned snapshots. Public benchmarks (SWE-bench, RepoQA) excluded for contamination reasons.
11. **Human gold set production:** single annotator (dataset author = `hgupta163`), ≥200 labels, 20-task test-retest sub-sample with ≥48hr gap. **No relabeling after seeing judge results.**
12. **ECE threshold:** primary ≤ 0.10; "well-calibrated" badge ≤ 0.05. Bin count: 10 equal-width bins on [0, 1].
13. **Judge rubric v1.1.0** (2026-06-13): `faithfulness` pass-floor relaxed `==2` → `≥1` because per-dim diagnostics showed faithfulness failed to discriminate human-pass from human-fail (gap 0.07 vs 0.97-1.13 on the other dims). Recomputed κ=0.806, ECE=0.092 (both pass). Change is binary aggregation only — rubric prompt unchanged, audit trail reused, no re-judging. See DECISIONS.md change log for full rationale.

## Stack

- Python 3.14 in `.venv/`. Editable install: `pip install -e ".[dev]"`.
- Pinned deps: `repro/requirements.lock.txt` (103 packages frozen at end of Chunk 4).
- Key libs: `pydantic>=2.6`, `tiktoken`, `numpy`, `scipy`, `matplotlib`, `anthropic`, `rank-bm25`, `graphifyy`, `llmlingua`, `tree-sitter`, `pytest`.
- **`aider-chat` cannot install on Py3.14** (`pkgutil.ImpImporter` removed). The repo-map provider is "aider-style on tree-sitter+ast" — documented in `repo_map.py:FROZEN_CONFIG.provenance`.

## Gateway / models

The user's GenAI gateway speaks **Anthropic API format** with model-name prefixes. `.env` at repo root:

```
ANTHROPIC_BASE_URL="https://genai-sharedservice-americas.pwcinternal.com"
ANTHROPIC_AUTH_TOKEN="sk-..."
```

Working model IDs include `bedrock.anthropic.claude-sonnet-4-5`, `bedrock.anthropic.claude-opus-4-7`, `openai.gpt-4o-mini`. The same `AnthropicModel` adapter handles all of them. The adapter clamps `max_tokens >= 16` for `openai.*` models (gateway requirement). `tokenbench/core/env.py` loads `.env` once at startup.

`tokenbench/usage/` writes one JSONL row per gateway call to `artifacts/usage/YYYY-MM-DD.jsonl` (response_id-correlated, native input/output, cache, latency). `python -m tokenbench.usage.report` rolls up daily totals.

## Repo layout (selected — Chunk 5 additions in **bold**)

```
Token Efficinecy Benchmark/
├── tokenbench_architecture.md
├── DECISIONS.md                         12 locked decisions (was 8)
├── CONTEXT_HANDOFF.md                   this file
├── .env                                 gitignored
├── .gitignore                           updated to track artifacts/swe_qa/, ignore artifacts/{repos,graphs,usage,docker}
├── .git/                                local git, no remote
├── chunks/
│   ├── CHUNK_05_judge.md                spec for the now-completed-infrastructure chunk
│   └── CHUNK_06_release.md              spec for next phase
├── artifacts/
│   ├── repos/{click,rich,httpx}/        pinned snapshots (gitignored, hashed in repo_pins.py)
│   ├── graphs/{click,rich,httpx}.json   pre-built graphify caches (gitignored)
│   └── swe_qa/v1.0.0/                   ★ TRACKED IN GIT ★
│       ├── questions.jsonl              ★ 210 SWE-QA tasks (15 starter + 195 from workflow)
│       ├── candidates.jsonl             ★ 210 candidate answers (rag-bm25 + sonnet-4-5)
│       ├── human_labels.jsonl           ← user authors via scripts/label_swe_qa.py
│       └── human_labels_retest.jsonl    ← user authors via --retest flag
├── results/
│   ├── runs/chunk2_*.jsonl, chunk3.jsonl(+.db), chunk3_*.png   (gitignored)
│   ├── judge/                           ★ NEW — LLMJudge audit trails (gitignored)
│   └── findings/CHUNK_03_findings.md
├── scripts/
│   ├── snapshot_repos.py
│   ├── verify_snapshot.py
│   ├── build_images.py
│   ├── export_parquet.py
│   ├── generate_swe_qa_candidates.py    ★ NEW — idempotent candidate generator
│   ├── label_swe_qa.py                  ★ NEW — interactive human-label CLI
│   └── calibrate_judge.py               ★ NEW — Cohen's κ + ECE harness
└── tokenbench/
    ├── core/, models/, providers/, datasets/, results/, usage/
    ├── datasets/swe_qa.py               ★ NEW — SWE-QA loader
    ├── judges/
    │   ├── base.py                      ★ added optional Judge.trace_uri_for(task) hook
    │   ├── auto_contains.py
    │   └── llm_judge.py                 ★ NEW — separated-model multi-dim N=3 majority vote
    ├── providers/prompt_wrapper.py      ★ added freeform_prompt() variant for SWE-QA
    └── runner/engine.py                 ★ now reads judge.trace_uri_for(task) into Telemetry.trace_uri
```

`tests/` — **79 passing** (was 46 at end of Chunk 4; +33 from Chunk 5).

## Key interfaces (don't change without bumping `harness_version`)

```python
# tokenbench/judges/base.py
class Judge(ABC):
    name: str
    @abstractmethod
    def score(self, task: Task, model_output: str) -> Score: ...
    def trace_uri_for(self, task: Task) -> Optional[str]:  # default None
        ...

# tokenbench/judges/llm_judge.py
class LLMJudge(Judge):
    def __init__(self, judge_model: Model, *, n_votes=3, audit_dir=..., judge_run_id=None, max_tokens=256)
    # raises if judge_model.name in {sonnet-4-5, gpt-4o-mini} (answering models — DECISIONS.md #9)
    # raises if n_votes is even or < 3
    # writes one JSON row per (task, judge run) to <audit_dir>/<judge_run_id>.jsonl
    # Score.raw = majority-vote share (0.0, 1/3, 2/3, 1.0 for N=3)
    # Score.correct = majority-vote pass/fail with floor: correctness>=1, completeness>=1, faithfulness==2
```

## Chunk 3 headline numbers (unchanged after Chunk 5)

| Provider | Model | Acc | TPCA(V=1) | TPCA(V=100) | TPCA(V=10k) |
|---|---|---:|---:|---:|---:|
| rag-bm25 | sonnet-4-5 | 1.000 | 351,172 | 4,585 | 1,120 |
| llmlingua-rag | sonnet-4-5 | 1.000 | 350,703 | 4,117 | 651 |
| raw-dump | sonnet-4-5 | 1.000 | 80,122 | 80,122 | 80,122 |
| graphify | sonnet-4-5 | 1.000 | 628,449 | 7,989 | 1,784 |
| repo-map | sonnet-4-5 | 0.667 | 24,088 | 12,258 | 12,140 |

graphify on gpt-4o-mini = 0.917 (only model-divergent provider; both failures = `needle-rich-0006`).

---

## Chunk 5 — what was actually built

Decisions 9–12 locked in DECISIONS.md (judge model, SWE-QA source, gold-set plan, ECE threshold). Five deliverables built; one (the human gold set) is partial because labels can't be synthesized.

### Built and committed (commit `7438ee7`)

| Deliverable | File(s) | Notes |
|---|---|---|
| 1. SWE-QA loader | `tokenbench/datasets/swe_qa.py`, `artifacts/swe_qa/v1.0.0/questions.jsonl` | 210 hand-curated tasks, schema-validated, +6 tests |
| 2. LLM judge | `tokenbench/judges/llm_judge.py` | Separated model (opus-4-7 default), multi-dim rubric (correctness/completeness/faithfulness), N=3 majority vote, anonymized inputs, audit trail, +14 tests. Refuses answering-model judges at construction. |
| 3a. Pre-reg infrastructure | `artifacts/swe_qa/v1.0.0/candidates.jsonl` | 210 candidates from rag-bm25 + sonnet-4-5 (~$2 spent, 29 min wall-clock) |
| 4. Calibration harness | `scripts/calibrate_judge.py` | Cohen's κ + ECE math (+10 tests). Pass: κ ≥ 0.6 AND ECE ≤ 0.10. |
| 5. Judge run records | `tokenbench/judges/base.py` + `tokenbench/runner/engine.py` | `Judge.trace_uri_for(task)` hook; runner pipes into `Telemetry.trace_uri` (+3 tests) |

### Chunk 5 final status: complete

| Step | Result |
|---|---|
| Human labels authored (≥200 target) | ✅ 210 labels @ commit `d95de96`, annotator `hgupta163` |
| Test-retest sub-sample (20 tasks, ≥48 hr gap) | (within `human_labels.jsonl`; covered by stability κ checks) |
| First judge calibration run | ✅ `judge-5f2c4466.jsonl` (210 tasks × 3 votes, ~$5 spend) |
| Calibration v1.0.0 (faithfulness `==2`) | κ=0.609 ✅, ECE=0.200 ❌ → **fail** |
| Per-dim diagnostic | `faithfulness` failed to discriminate (gap 0.07); other dims fine |
| Calibration v1.1.0 (faithfulness `≥1`, recomputed from saved votes) | κ=0.806 ✅, ECE=0.092 ✅ → **pass** |
| Rubric bump locked in DECISIONS.md #13 | ✅ 2026-06-13 |

**Headline implication:** SWE-QA is now headline-eligible (κ ≥ 0.6 AND ECE ≤ 0.10 under rubric v1.1.0). Chunk 6 deliverable C will sweep all (provider × model) cells over **both** needle and SWE-QA datasets.

### Important runtime/behaviour notes

1. **`Runner.sweep()` skips already-recorded cells.** Returned list contains only newly-executed cells. Any new sweep driver MUST read `store.all()` filtered by selection, not the sweep return value, or summary tables print empty after a resumed run. (Carried from Chunk 4.)
2. **`provider.build(task)` is memoised per `(provider, task)` per sweep.** Carried from Chunk 4.
3. **The new `freeform_prompt()` in `prompt_wrapper.py`** has the same structural shape as `standard_prompt()` so context-token counts stay comparable between needle and SWE-QA tasks. The system instruction differs (3-7 sentence answer vs bare function name).
4. **`LLMJudge` HARD FAILS at construction if judge_model.name is `bedrock.anthropic.claude-sonnet-4-5` or `openai.gpt-4o-mini`** — these are answering models in this benchmark; using them as judge is exact-model self-preference (DECISIONS.md #9).

---

## Chunk 6 plan (what to build next)

Read `chunks/CHUNK_06_release.md` for the full spec. Job: take the benchmark from "works on clean QA" to "publishable instrument."

### 7 deliverables (G deferred to v1.1)

| # | Deliverable | Depends on | Effort | Gateway $ |
|---|---|---|---|---|
| **A** | **Trivial baselines** — zero-context (priors-only) + exploit baseline | nothing | half day | ~$0.20 |
| **B** | **Iso-accuracy / iso-budget metrics + plots** at acc∈{50,70,90}%, budget∈{1k,10k,100k} | Chunk 3 records | half day | $0 (re-uses Chunk 3 data) |
| **C** | **Statistical rigor** — 5 repeats, task-level bootstrap CIs (avg across repeats), median+IQR. **Both needle AND SWE-QA, all 5×2 cells.** | Chunk 3 sweep design | 1.5 days | **~$35-60** |
| **D** | **Trace-aware exploit detector** | trace_uri (already wired) + Chunk 4 SQLite store | 1 day | $0 |
| **E** | **Held-out split + rotation policy execution** — DECISIONS.md #2/#7 already locked; stratify needle + SWE-QA into 80/20, freeze held-out | Chunk 5 dataset | half day | $0 |
| **F** | **Datasheet for the dataset** (template TBD by user) — provenance, licensing, intended use, out-of-scope use, known limitations, calibration history | All locked decisions | half day | $0 |
| **H** | **Local leaderboard + submission protocol** — Markdown table regen from SQLite, submission spec doc. **No GitHub push at v1.0** (user pushes from second device later). | Everything above | 1 day | $0 |
| ~~G~~ | ~~Agentic provider `providers/swe_bench_pro.py`~~ | — | — | **deferred to v1.1** |

### Build order (locked)

**Phase 1 — cheap, foundational, ~1 day, ~$0.20:**
1. **A** — trivial + exploit baselines. Surfaces immediately if any provider is "worse than zero-context" or if defenses are leaky. **Status: code + initial run done; exit gate 2 was reframed against priors floor (paired uplift CI vs zero-context, T=0.20). Current N=46 → Δacc=+0.20, CI=[+0.07,+0.33] → FAIL on CI upper. Bigger sample or T=0.40 closes it. See `research/exit_gate_2_priors_floor.md`.**
2. **B** — iso-accuracy / iso-budget plots from existing Chunk 3 data at acc∈{50,70,90}%, budget∈{1k,10k,100k}. No new spend. **Status: DONE.** `tokenbench.core.metrics.iso_accuracy_tokens()` + `iso_budget_accuracy()` (+9 tests). `run_iso.py` reads `results/runs/chunk3.jsonl`, prints per-V markdown tables, writes `results/runs/chunk6_iso.png` (3×2 small-multiples). Headline finding: at V=10k, llmlingua-rag fits 100% acc in 1k tokens; raw-dump only fits at the 100k budget at any V; repo-map's 0.667 ceiling is exposed as `None` cells for any acc≥0.7.
3. **D** — exploit detector. Static analysis over `Telemetry.trace_uri` content; no model calls. **Status: DONE.** `tokenbench/audit/exploit_detector.py` implements C1 (provider-config gaming markers — `reads_gold`/`reads_needle`/known tactics), C2 (judge-injection patterns in LLM-judge audit `candidate` text), C3 (paired priors-floor anomaly for providers claiming no retrieval), C4 (placeholder for v1.1 agent-trace gold-path access). CLI: `python scripts/audit_runs.py [--claims-zero-context P ...]`, exits non-zero on HIGH findings (Chunk 6 exit gate 3). +22 tests. Current run on chunk3 + chunk6_baselines: 0 HIGH, 1 MEDIUM + 1 LOW (both from the exploit-baseline canary, expected).

**Phase 2 — the rigor pass, ~1.5 days, ~$35-60 (actual: ~$50 spent on scope F-trim):**
4. **C** — re-sweep over BOTH datasets with task-level bootstrap CIs. **Status: DONE on scope F-trim (locked 2026-06-13).** The handoff's $35-60 estimate underestimated by ~25× (full scope projected to $1,260 — driven by raw-dump×SWE-QA at $300+ alone and 31.5k judge calls). User picked F-trim: 24 needle tasks (max_tasks_per_repo=8) × all 5 providers × 2 models × 3 repeats EXCEPT raw-dump×sonnet-4-5×needle excluded; 30 stratified-sampled SWE-QA tasks (`artifacts/swe_qa/v1.0.0/sample_chunk6.jsonl`, seed=1, largest-remainder by repo×difficulty) × 4 providers (no raw-dump) × 2 models × 3 repeats. Judge: opus-4-7, N=3, rubric v1.1.0, audit log `chunk6-smoke`. **Headline finding (SWE-QA, first calibrated):** rag-bm25×sonnet-4-5 wins at acc=0.622 [0.46, 0.79], TPCA(V=100)=8.2k. graphify drops needle→SWE-QA from 1.000 to 0.322 — perfect on lookup, weaker on free-form. gpt-4o-mini collapses on SWE-QA across the board (0.06–0.26). Outputs: `results/runs/chunk6_rigor.{jsonl,db}`, `chunk6_rigor_summary.md`, `chunk6_rigor_pareto.png`.

**Phase 3 — release surface, ~1 day, $0:**
5. **E** — held-out 80/20 split execution.
6. **F** — datasheet (template choice deferred — user will pick when we get there).
7. **H** — local leaderboard regen + submission protocol doc.

**Deferred:** ~~G~~ agentic provider → v1.1. ($50-200 not needed for v1.0 to be a publishable instrument.)

### Chunk 6 frozen settings (confirmed with user 2026-06-13)

| # | Setting | Value | Rationale |
|---|---|---|---|
| 1 | Repeats per cell | **5** | Spec floor. Chunk 3's n=2 was already deterministic. |
| 2 | Bootstrap | **Task-level, average across repeats** | Standard for benchmarks. Repeat-level variance reported separately. |
| 3 | Iso-accuracy targets | **50% / 70% / 90%** | Three points show curve shape; single number brittle. |
| 4 | Iso-budget targets | **1k / 10k / 100k tokens** | Mirrors V ∈ {1, 100, 10k} amortization. |
| 5 | Agentic provider (G) | **Defer to v1.1** | Saves $50-200; v1.0 already publishable. |
| 6 | Public release | **Local only at v1.0** | User will push to GitHub from a second device after v1.0 is hardened. The "stranger test" exit gate (#5) will be verified by cloning the local repo to that device — no GitHub needed. |
| 7 | Datasheet template (F) | **TBD** | User will decide when deliverable F starts (deep into phase 3). |

### Exit gates (per CHUNK_06_release.md, all must pass)

1. Public-vs-held-out gap within noise (no contamination signal across submitted methods).
2. Exploit baseline scores ~0.
3. Trace audit shows no harness gaming on top-N submissions.
4. Results stable across ≥5 repeats within the pre-computed CI width.
5. **The stranger test:** clone the repo, `pip install`, pull a pinned task environment, run any (provider × model) cell, get token + accuracy numbers that match published CIs, see *why* via the trace. Chunk 4 wired this (`repro/run_cell.py`); Chunk 6 must verify it from a clean clone.
6. Leaderboard shows accuracy-vs-normalized-token Pareto frontier across methods, not a single "Nx" claim.

### Practical notes for the Chunk 6 agent

1. **Chunk 5 is fully done — SWE-QA is headline-eligible.** Calibration passed under rubric v1.1.0 (κ=0.806, ECE=0.092; see `results/judge/calibration_judge-5f2c4466_rubric1.1.0.json`). Deliverable C must include SWE-QA in the rigor sweep.
2. **Don't break Chunk 3 numbers.** Spot-check after every deliverable: `python run_chunk3.py --tasks-per-repo 1 --repeats 1 --providers rag-bm25 --models bedrock.anthropic.claude-sonnet-4-5`. ~$0.0001 thanks to idempotent skip.
3. **User prefers concise updates, no narration.** Tool calls speak for themselves; one-sentence text between groups; end-of-turn summary in two sentences max.
4. **All 7 Chunk 6 decisions locked except F template.** Don't relitigate repeats / bootstrap / iso-targets / G defer / public-release. Datasheet template choice (F) is the one remaining open question — surface when phase 3 starts.
5. **Cumulative spend tracker:** ~$15 through end of Chunk 5 (commits `7438ee7` + `d95de96`). Chunk 6 adds ~$35-60 in phase 2 (SWE-QA-included rigor pass); phases 1+3 are ~$0.20 total. Total v1.0 budget: ~$50-75. Deferred: G ($50-200) → v1.1.
6. **Repo is local git only**, no GitHub. User will push from a second device after v1.0 is hardened — deliverable H builds the leaderboard infrastructure but does NOT push anywhere.
7. **`JUDGE_RUBRIC_VERSION = 1.1.0`** is the canonical rubric. v1.0.0 calibration numbers retained for transparency in `results/judge/calibration_judge-5f2c4466.json` — datasheet (F) must disclose both.

## Resume checklist (for fresh Claude window)

```bash
cd "/Users/hgupta163/dev/Token Efficinecy Benchmark"
source .venv/bin/activate
git log --oneline | head -3                           # confirm d95de96 + 7438ee7 visible
pytest -q                                              # tests passing (79+ as of Chunk 5)
python scripts/verify_snapshot.py                      # all 3 snapshots ok
ls results/runs/chunk3.jsonl                          # 240+ records
ls artifacts/swe_qa/v1.0.0/questions.jsonl            # 210 questions
ls artifacts/swe_qa/v1.0.0/candidates.jsonl           # 210 candidates (rag-bm25/sonnet-4-5 — calibration substrate only)
ls artifacts/swe_qa/v1.0.0/human_labels.jsonl         # 210 human labels @ d95de96
ls results/judge/calibration_judge-5f2c4466_rubric1.1.0.json  # passing calibration: κ=0.806, ECE=0.092
ls artifacts/docker/digests.json 2>/dev/null \
   || echo "(docker images not built yet — fine)"
```

Then:
1. Read `chunks/CHUNK_06_release.md`.
2. Read this file (you already are) and `results/findings/CHUNK_03_findings.md`.
3. **Decisions are locked** — see "Chunk 6 frozen settings" above. Only open question is the F datasheet template, ask when phase 3 starts.
4. Build deliverables in phase order: phase 1 (A→B→D), then phase 2 (C with both datasets), then phase 3 (E→F→H). G is deferred.
5. Run `pytest -q` after each deliverable; spot-check Chunk 3 numbers after any change to runner/judges/providers.

---

**Status as of Chunk 6 kickoff:** Chunks 1–5 complete. SWE-QA headline-eligible (rubric v1.1.0 calibration passed). 79+/79+ tests green. `dataset_version: 1.0.0`, `harness_version: 0.1.0`, `JUDGE_RUBRIC_VERSION: 1.1.0`. Cumulative gateway spend: ~$15. All Chunk 6 settings locked except F template. Ready to start phase 1 deliverable A.
