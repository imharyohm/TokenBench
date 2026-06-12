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
| 5 — Free-form QA + judge calibration | **PARTIAL — needs human labels** | Infrastructure done; 200 labels are user's work to author |
| 6 — Release | NEXT | Trivial baselines, iso-acc/iso-budget, ≥5-repeat rigor pass, exploit detector, held-out split, datasheet, leaderboard, agentic provider |

`dataset_version: 1.0.0`, `harness_version: 0.1.0`. Cumulative gateway spend: **~$9.72** (Chunks 2–3 ~$7.72 + Chunk 5 candidate generation ~$2).

**Repo is now under local git** (initialized 2026-06-10, no remote). Pre-registration boundary is commit `7438ee7` — any commit adding `artifacts/swe_qa/v1.0.0/human_labels.jsonl` will appear strictly after, satisfying Chunk 5 exit gate 4.

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

### NOT BUILT YET — needs the user

**Deliverable 3 (human gold set) is in progress.** Requires:

1. **`hgupta163` runs `python scripts/label_swe_qa.py --annotator hgupta163`** — walks through 210 (question, reference, candidate) triples, labels pass/fail. Resumable, idempotent. Estimated 5 hours total. Goal: ≥200 labels with annotator id + ISO timestamp.

2. **≥48hr later, run `python scripts/label_swe_qa.py --annotator hgupta163 --retest <task_id>`** for 20 random task_ids. Writes to `human_labels_retest.jsonl`. Used for within-rater stability κ (proxy for inter-rater since we have one annotator).

3. **Commit both files to git.** Will appear in `git log` strictly after `7438ee7`, proving labels were authored after pre-registration was locked.

4. **Run `python scripts/calibrate_judge.py --version 1.0.0`** — first real opus-4-7 spend. ~$3-6 for 200 tasks × 3 votes. Emits κ + ECE verdict.

**The user explicitly said they cannot have Claude do the labels** — that would invalidate κ (Claude judging Claude's own family ≈ 1.0 trivially). Per DECISIONS.md #11, "single annotator (dataset author)". Three legitimate paths if labeling time is unavailable:

- **(a)** User labels all 200 over multiple sessions
- **(b)** Smaller pilot (e.g. 50) — produces unstable κ (CI ±0.15+); SWE-QA flagged exploratory only
- **(c)** Skip labels entirely — Chunk 5 exit gate 1 explicitly allows this; SWE-QA stays exploratory; headline TPCA continues using auto-scored needle datasets (which already give 4 publishable findings from Chunk 3)

The Chunk 5 spec was designed with (c) as the legitimate fallback. **Chunk 6 is not blocked on this**; it can run in parallel.

### Important runtime/behaviour notes

1. **`Runner.sweep()` skips already-recorded cells.** Returned list contains only newly-executed cells. Any new sweep driver MUST read `store.all()` filtered by selection, not the sweep return value, or summary tables print empty after a resumed run. (Carried from Chunk 4.)
2. **`provider.build(task)` is memoised per `(provider, task)` per sweep.** Carried from Chunk 4.
3. **The new `freeform_prompt()` in `prompt_wrapper.py`** has the same structural shape as `standard_prompt()` so context-token counts stay comparable between needle and SWE-QA tasks. The system instruction differs (3-7 sentence answer vs bare function name).
4. **`LLMJudge` HARD FAILS at construction if judge_model.name is `bedrock.anthropic.claude-sonnet-4-5` or `openai.gpt-4o-mini`** — these are answering models in this benchmark; using them as judge is exact-model self-preference (DECISIONS.md #9).

---

## Chunk 6 plan (what to build next)

Read `chunks/CHUNK_06_release.md` for the full spec. Job: take the benchmark from "works on clean QA" to "publishable instrument."

### 8 deliverables

| # | Deliverable | Depends on | Effort | Gateway $ |
|---|---|---|---|---|
| **A** | **Trivial baselines** — zero-context (priors-only) + exploit baseline | nothing | half day | ~$0.20 |
| **B** | **Iso-accuracy / iso-budget metrics + plots** | Chunk 3 records | half day | $0 (re-uses Chunk 3 data) |
| **C** | **Statistical rigor** — ≥5 repeats, bootstrap CIs over (tasks × repeats), median+IQR | Chunk 3 sweep design | 1 day | ~$15-25 |
| **D** | **Trace-aware exploit detector** | trace_uri (already wired) + Chunk 4 SQLite store | 1 day | $0 |
| **E** | **Held-out split + rotation policy execution** — DECISIONS.md #2/#7 already locked; stratify needle + SWE-QA into 80/20, freeze held-out | Chunk 5 dataset | half day | $0 |
| **F** | **Datasheet for the dataset** (Gebru et al. template) — provenance, licensing, intended use, out-of-scope use, known limitations | All locked decisions | half day | $0 |
| **G** | **`providers/swe_bench_pro.py`** — agentic provider, telemetry-only | Trace audit (D) + agent SDK access | 2 days | **$50-200** |
| **H** | **Public leaderboard + submission protocol** — Markdown table regen from SQLite, submission spec doc | Everything above | 1 day | $0 |

### Build order

**Phase 1 — cheap, foundational, ~1 day, ~$0.20:**
1. **A** — trivial + exploit baselines. Surfaces immediately if any provider is "worse than zero-context" or if defenses are leaky.
2. **B** — iso-accuracy / iso-budget plots from existing Chunk 3 data. No new spend.
3. **D** — exploit detector. Static analysis over `Telemetry.trace_uri` content; no model calls.

**Phase 2 — the rigor pass, ~1 day, ~$15-25:**
4. **C** — re-sweep at ≥5 repeats with bootstrap CIs. Uses Chunk 4's idempotent runner + parallel concurrency.

**Phase 3 — release surface, ~1.5 days, $0:**
5. **E** — split execution.
6. **F** — datasheet.
7. **H** — leaderboard + submission protocol.

**Phase 4 — expensive optional, ~2 days, $50-200:**
8. **G** — agentic provider. **Gate first** before kicking off. Could defer to v1.1.

### Open decisions to surface BEFORE Chunk 6 work begins (ask user)

These are flagged here so the next agent can confirm them before writing code:

1. **Repeat count for the rigor pass.** Spec says ≥5; doing 5 vs 10 changes cost ~2×. Recommend 5 (already at floor; Chunk 3's 2 repeats showed strong determinism).
2. **Bootstrap method.** Task-level (resample tasks, recompute κ/TPCA), or task×repeat (paired). Recommend **task-level with within-task averaging across repeats** for headline; report repeat-level variance separately.
3. **Iso-accuracy target value(s).** Recommend reporting at **50%/70%/90%** (single number is brittle).
4. **Iso-budget target value(s).** Recommend **1k / 10k / 100k** tokens; matches V ∈ {1, 100, 10k}.
5. **Agentic provider (deliverable G) — go/no-go.** $50-200 to show TokenBench works as a measurement instrument across context methods AND agent loops. Alternative: defer to v1.1.
6. **Release surface.** Public GitHub now (with held-out stripped) or local-only until v1.0 is hardened? User preferred local for the pre-registration; Chunk 6 needs public visibility for the leaderboard exit gate.
7. **Datasheet template.** Gebru et al. canonical template, or shortened version focused on the things this benchmark uniquely needs (held-out, canary, frozen-config provenance)?

### Exit gates (per CHUNK_06_release.md, all must pass)

1. Public-vs-held-out gap within noise (no contamination signal across submitted methods).
2. Exploit baseline scores ~0.
3. Trace audit shows no harness gaming on top-N submissions.
4. Results stable across ≥5 repeats within the pre-computed CI width.
5. **The stranger test:** clone the repo, `pip install`, pull a pinned task environment, run any (provider × model) cell, get token + accuracy numbers that match published CIs, see *why* via the trace. Chunk 4 wired this (`repro/run_cell.py`); Chunk 6 must verify it from a clean clone.
6. Leaderboard shows accuracy-vs-normalized-token Pareto frontier across methods, not a single "Nx" claim.

### Practical notes for the Chunk 6 agent

1. **Chunk 5's human labels may or may not be done.** Check `artifacts/swe_qa/v1.0.0/human_labels.jsonl`:
   - **If file exists with ≥200 rows AND there's a calibration report at `results/judge/calibration_*.json` with κ ≥ 0.6 AND ECE ≤ 0.10:** SWE-QA is calibrated; include it in headline TPCA.
   - **Otherwise:** SWE-QA stays exploratory; headline TPCA uses needle-codebase only. This is the legitimate fallback path per Chunk 5 exit gate 1.
2. **Don't break Chunk 3 numbers.** Spot-check after every deliverable: `python run_chunk3.py --tasks-per-repo 1 --repeats 1 --providers rag-bm25 --models bedrock.anthropic.claude-sonnet-4-5`. ~$0.0001 thanks to idempotent skip.
3. **User prefers concise updates, no narration.** Tool calls speak for themselves; one-sentence text between groups; end-of-turn summary in two sentences max.
4. **User wants to be in the loop on big choices.** Specifically for Chunk 6: deliverable G (agentic provider) cost gate, public-release gate, repeat count, iso-target values, datasheet template choice.
5. **Cumulative spend tracker:** ~$9.72 through Chunk 5 commit `7438ee7`. Chunk 6 phases 1+2 add ~$15-25; phase 4 (optional) adds $50-200.
6. **Repo is local git only**, no GitHub. The user explicitly asked to keep it local for the Chunk 5 pre-registration. Public-release gate is Chunk 6 deliverable H — confirm before pushing anywhere.

## Resume checklist (for fresh Claude window)

```bash
cd "/Users/hgupta163/dev/Token Efficinecy Benchmark"
source .venv/bin/activate
git log --oneline | head -3                           # confirm 7438ee7 visible
pytest -q                                              # 79 passing
python scripts/verify_snapshot.py                      # all 3 snapshots ok
ls results/runs/chunk3.jsonl                          # 240+ records
ls artifacts/swe_qa/v1.0.0/questions.jsonl            # 210 questions
ls artifacts/swe_qa/v1.0.0/candidates.jsonl           # 210 candidates
ls artifacts/swe_qa/v1.0.0/human_labels.jsonl 2>/dev/null \
   && echo "labels present — check calibration" \
   || echo "labels not yet authored — Chunk 6 proceeds with SWE-QA exploratory"
ls artifacts/docker/digests.json 2>/dev/null \
   || echo "(docker images not built yet — fine)"
```

Then:
1. Read `chunks/CHUNK_06_release.md`.
2. Read this file (you already are) and `results/findings/CHUNK_03_findings.md`.
3. Confirm with user: repeat count, iso-target values, agentic-provider go/no-go, public-release gate, datasheet template.
4. Build deliverables in phase order (A→B→D, then C, then E→F→H, then G if approved).
5. Run `pytest -q` after each deliverable; spot-check Chunk 3 numbers after any change to runner/judges/providers.

---

**Status as of Chunk 5 handoff:** Chunks 1–4 complete; Chunk 5 infrastructure complete; human labels pending user time. 79/79 tests green. `dataset_version: 1.0.0`, `harness_version: 0.1.0`. Cumulative gateway spend: ~$9.72. Ready for Chunk 6.
