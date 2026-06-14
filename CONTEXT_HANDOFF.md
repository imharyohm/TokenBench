# TokenBench — Context Handoff for v1.0 close-out

> Paste this whole file (or attach it) into a fresh Claude window when resuming. Self-contained — no need to re-read the architecture doc, chunk specs, or transcript unless something is unclear.

---

## What we're building

A **measurement instrument** for codebase-context token efficiency. Runs context methods (RAG, Graphify, repo-map, LLMLingua, raw-dump) through a fixed model on auto-scored and LLM-judged tasks, captures normalized token counts, and produces an accuracy-vs-tokens Pareto frontier with build-cost amortization at V ∈ {1, 100, 10000}.

It is **not** a predictor or claim verifier. It's a scale. The user reads the curve and decides which method fits their query volume / accuracy regime.

Reference docs: `tokenbench_architecture.md`, `DECISIONS.md`, `chunks/CHUNK_*.md`, `DATASHEET.md`, `LEADERBOARD.md`, `SUBMISSION.md`, `research/v1_0_close_out_plan.md`, `research/exit_gate_2_priors_floor.md`, `research/agentic_provider_deferred.md`.

## Status

| Chunk | Status | Headline |
|---|---|---|
| 1 — Skeleton + metric math + locked decisions | DONE | mocks-only, 33 tests |
| 2 — Real Anthropic adapter, BM25 RAG, pinned-repo dataset | DONE | rag-bm25 12/12 acc, byte-identical reruns |
| 3 — 5 providers × 2 models × 240-cell sweep | DONE | Pareto + amortization plots, 4 exit gates pass |
| 4 — Reproducibility hardening (snapshot verifier, Docker scaffolding, idempotent/resumable/parallel runner, SQLite mirror, repro/) | DONE | 46 tests, 3/4 exit gates verified by automated test |
| 5 — Free-form QA + judge calibration | DONE | 210 human labels @ commit `d95de96`; judge calibrated under rubric v1.1.0 (κ=0.806, ECE=0.092); SWE-QA headline-eligible |
| 6 — Release | **DONE pending v1.0 close-out** | A+B+D, C (rigor sweep ~$50), E (split), F (datasheet), H (leaderboard + submission) all built and committed. 3 of 6 exit gates verified; 3 remain. |
| **v1.0 tag** | **NEXT** | Close gates #1, #4, #5 per `research/v1_0_close_out_plan.md`. Recommended scope L: ~$13. Then `git tag v1.0.0`. |

`dataset_version: 1.0.0`, `harness_version: 0.1.0`, `JUDGE_RUBRIC_VERSION: 1.1.0`. Cumulative gateway spend: **~$65** (Chunks 2–3 ~$7.72 + Chunk 5 ~$7 + Chunk 6 Phase 1 baselines ~$0.50 + Chunk 6 Phase 2 rigor sweep ~$50).

**Repo is local git only** (initialized 2026-06-10, no remote). Pre-registration boundary `7438ee7` (labels not yet authored) → labels committed at `d95de96`. **User plans to push to GitHub later from a second device** (not at v1.0).

## Locked decisions (do not relitigate — see `DECISIONS.md`)

1. **Tokenizer:** `o200k_base` via `tiktoken`. Every `*_norm` field uses this encoder.
2. **Public/held-out split:** 80/20, stratified by language and repo size for needle, by repo×difficulty for SWE-QA. Held-out kept private. **Frozen at commit `f1ad5e7`.**
3. **Isolation boundary:** scoring runs outside the agent container; gold answers never enter the agent's context.
4. **Run records:** append-only, immutable, versioned by `(dataset_version, harness_version, provider_version, model)`.
5. **Build cost amortization:** report TPCA at V ∈ {1, 100, 10000}. A single TPCA without a stated V is forbidden for any method with non-zero build cost.
6. **Method fairness:** **FROZEN PUBLISHED CONFIGS.** No tuning. Switching to equal-budget needs a new `dataset_version`.
7. **Held-out rotation:** 12-month cadence; early-rotate if public-vs-held gap > 2× CI or canary leaks.
8. **Model adapter:** all model providers conform to `tokenbench.models.base.Model` (single chokepoint for native-token capture + o200k re-count + trace).
9. **Judge model:** `bedrock.anthropic.claude-opus-4-7`. Must differ from any answering model. Within-family bias risk mitigated by anonymized inputs + 20-task `openai.gpt-4o` robustness check.
10. **SWE-QA source:** hand-curated against pinned snapshots. Public benchmarks (SWE-bench, RepoQA) excluded for contamination reasons.
11. **Human gold set production:** single annotator (`hgupta163`), ≥200 labels, 20-task test-retest sub-sample with ≥48hr gap. **No relabeling after seeing judge results.**
12. **ECE threshold:** primary ≤ 0.10; "well-calibrated" badge ≤ 0.05. Bin count: 10 equal-width bins on [0, 1].
13. **Judge rubric v1.1.0** (2026-06-13): `faithfulness` pass-floor relaxed `==2` → `≥1`. Recomputed κ=0.806, ECE=0.092 (both pass). Detail in DECISIONS.md change log.

## Stack

- Python 3.14 in `.venv/`. Editable install: `pip install -e ".[dev]"`.
- Pinned deps: `repro/requirements.lock.txt` (103 packages frozen at end of Chunk 4).
- Key libs: `pydantic>=2.6`, `tiktoken`, `numpy`, `scipy`, `matplotlib`, `anthropic`, `rank-bm25`, `graphifyy`, `llmlingua`, `tree-sitter`, `pytest`.
- **`aider-chat` cannot install on Py3.14**. The repo-map provider is "aider-style on tree-sitter+ast" — documented in `repo_map.py:FROZEN_CONFIG.provenance`.

## Gateway / models

The user's GenAI gateway speaks **Anthropic API format** with model-name prefixes. `.env` at repo root:

```
ANTHROPIC_BASE_URL="https://genai-sharedservice-americas.pwcinternal.com"
ANTHROPIC_AUTH_TOKEN="sk-..."
```

Working model IDs include `bedrock.anthropic.claude-sonnet-4-5`, `bedrock.anthropic.claude-opus-4-7`, `openai.gpt-4o-mini`. The same `AnthropicModel` adapter handles all of them. The adapter clamps `max_tokens >= 16` for `openai.*` models (gateway requirement). `tokenbench/core/env.py` loads `.env` once at startup.

## Repo layout (selected — Chunk 6 additions in **bold**)

```
Token Efficinecy Benchmark/
├── tokenbench_architecture.md
├── DECISIONS.md                         13 locked decisions
├── CONTEXT_HANDOFF.md                   this file
├── DATASHEET.md                         ★ Gebru-template, Q1–Q40 + addenda
├── LEADERBOARD.md                       ★ regenerated from chunk6_rigor.jsonl
├── SUBMISSION.md                        ★ v1.0 submission contract
├── .env                                 gitignored
├── .gitignore                           tracks public splits, ignores _heldout/
├── .git/                                local git, no remote
├── chunks/CHUNK_*.md                    chunk specs (5 done, 6 nearly done)
├── artifacts/
│   ├── repos/{click,rich,httpx}/        pinned snapshots (gitignored)
│   ├── graphs/{click,rich,httpx}.json   pre-built graphify caches (gitignored)
│   ├── swe_qa/v1.0.0/                   ★ TRACKED IN GIT ★
│   │   ├── questions.jsonl                  210 SWE-QA tasks
│   │   ├── candidates.jsonl                 210 calibration candidates
│   │   ├── human_labels.jsonl               210 human labels @ d95de96
│   │   ├── human_labels_retest.jsonl        20-task retest sub-sample
│   │   ├── sample_chunk6.jsonl          ★ 30 stratified rigor-sweep tasks
│   │   └── public_split.tsv             ★ 168 SWE-QA public task_ids
│   ├── needle/v1.0.0/public_split.tsv   ★ 240 needle public task_ids
│   └── _heldout/                        ★ GITIGNORED — never distribute
│       ├── needle/v1.0.0/heldout_split.tsv      60 task_ids
│       └── swe_qa/v1.0.0/heldout_split.tsv      42 task_ids
├── results/
│   ├── runs/                            (gitignored)
│   │   ├── chunk3.jsonl                     243 records, baseline Pareto
│   │   ├── chunk6_baselines.jsonl           92 records, A baselines
│   │   ├── chunk6_rigor.jsonl           ★ 1,386 records, the rigor sweep
│   │   ├── chunk6_rigor_summary.md      ★
│   │   ├── chunk6_rigor_pareto.png      ★
│   │   └── chunk6_iso.png               ★ B iso-acc/iso-budget plot
│   ├── judge/                           (gitignored, audit logs)
│   └── findings/CHUNK_03_findings.md
├── repro/                               Chunk 4 — stranger-test entrypoint
│   ├── Makefile                             `make repro TASK=<id>`
│   ├── README.md
│   ├── requirements.lock.txt
│   └── run_cell.py
├── research/
│   ├── exit_gate_2_priors_floor.md      ★ reframed exploit gate
│   ├── agentic_provider_deferred.md     ★ G → v1.1 sizing
│   └── v1_0_close_out_plan.md           ★ THIS SESSION'S PLAN
├── scripts/
│   ├── (Chunk 4) snapshot_repos.py, verify_snapshot.py, build_images.py, export_parquet.py
│   ├── (Chunk 5) generate_swe_qa_candidates.py, label_swe_qa.py, calibrate_judge.py, diagnose_ece.py
│   ├── (Chunk 6) audit_runs.py            ★ exploit detector CLI
│   ├── (Chunk 6) sample_swe_qa.py         ★ stratified sampler
│   ├── (Chunk 6) freeze_splits.py         ★ public/held-out generator
│   └── (Chunk 6) generate_leaderboard.py  ★ LEADERBOARD.md regen
├── run_chunk3.py
├── run_baselines.py                     ★ Chunk 6 A
├── run_iso.py                           ★ Chunk 6 B
├── run_chunk6_rigor.py                  ★ Chunk 6 C — supports --dry-run
└── tokenbench/
    ├── core/, models/, datasets/, results/, usage/
    ├── audit/                           ★ NEW — exploit detector module
    │   ├── __init__.py
    │   └── exploit_detector.py
    ├── datasets/
    │   ├── splits.py                    ★ NEW — 80/20 splitter
    │   └── swe_qa.py
    ├── judges/{base.py, auto_contains.py, llm_judge.py}
    ├── providers/
    │   ├── (Chunks 2-3) rag.py, raw_dump.py, repo_map.py, graphify.py, llmlingua.py
    │   ├── zero_context.py              ★ NEW — priors floor
    │   ├── exploit_baseline.py          ★ NEW — gaming canary
    │   └── prompt_wrapper.py
    └── runner/engine.py
```

`tests/` — **146 passing** (was 79 at end of Chunk 5; +67 across Chunk 6).

## Key interfaces (don't change without bumping `harness_version`)

```python
# tokenbench/judges/base.py
class Judge(ABC):
    @abstractmethod
    def score(self, task: Task, model_output: str) -> Score: ...
    def trace_uri_for(self, task: Task) -> Optional[str]:
        ...

# tokenbench/judges/llm_judge.py
class LLMJudge(Judge):
    def __init__(self, judge_model: Model, *, n_votes=3, audit_dir=..., judge_run_id=None, max_tokens=256)
    # raises if judge_model.name in {sonnet-4-5, gpt-4o-mini}
    # raises if n_votes is even or < 3
    # writes one JSON row per (task, judge run) to <audit_dir>/<judge_run_id>.jsonl
    # rubric v1.1.0: PASS_FLOOR = {correctness>=1, completeness>=1, faithfulness>=1}

# tokenbench/audit/exploit_detector.py
def scan_records(records, *, claims_zero_context=(), tolerance=0.20) -> list[Finding]
# C1 config gaming markers, C2 judge-injection in candidates, C3 priors-floor anomaly,
# C4 v1.1 placeholder for agent-trace gold-path access.
# CLI: `python scripts/audit_runs.py` — exits non-zero on HIGH findings.

# tokenbench/datasets/splits.py
HELDOUT_FRACTION = 0.20  # locked, DECISIONS.md #2
def assign_splits(items, *, stratum_keys, fraction=0.20) -> list[SplitAssignment]
# Deterministic largest-remainder + sort-by-task_id (NO random seed).

# tokenbench/core/metrics.py — added in Chunk 6
def paired_uplift_ci(records_a, records_b, *, n_resamples=10_000, ...) -> PairedUplift
def iso_accuracy_tokens(records_by_method, target_acc, *, V=1.0) -> list[IsoAccuracyPoint]
def iso_budget_accuracy(records_by_method, budget_tokens, *, V=1.0) -> list[IsoBudgetPoint]
```

## Headline numbers (post-Chunk-6 rigor sweep, public split)

**Needle (auto-scored, n_tasks=8 per cell after public-split filter):**

| Provider × sonnet-4-5 | acc | TPCA(V=1) | TPCA(V=10k) | Pareto★? |
|---|---:|---:|---:|---|
| rag-bm25 | 1.000 | 257,824 | 1,145 | |
| llmlingua-rag | 0.875 | 294,061 | 713 | |
| repo-map | 1.000 | 16,023 | 8,055 | ★ |
| graphify | 1.000 | 112,934 | 1,537 | |
| raw-dump (gpt-4o-mini only) | 1.000 | 80,086 | 80,086 | |

**SWE-QA (calibrated judge, n_tasks=25 per cell after public-split filter):**

| Provider × sonnet-4-5 | acc | 95% CI | TPCA(V=1) | TPCA(V=10k) | Pareto★? |
|---|---:|---|---:|---:|---|
| **rag-bm25** | **0.622** | [0.46, 0.79] | 538,997 | 1,944 | ★ |
| llmlingua-rag | 0.480 | [0.29, 0.67] | 777,546 | 1,802 | |
| repo-map | 0.387 | [0.21, 0.56] | 41,974 | 21,375 | ★ |
| graphify | 0.347 | [0.18, 0.51] | 2,111,562 | 6,994 | |

gpt-4o-mini collapses on SWE-QA (0.06–0.26 across all four providers); on needle the gap is small.

Three diagnostic findings: (1) zero-context priors floor on needle/sonnet-4-5 = 0.26; (2) `auto_contains` short-needle leniency lifts exploit-baseline +0.20 over floor without gold reads; (3) build-cost amortization changes Pareto rankings — at V=1 raw-dump beats every retrieval method on tokens-per-correct, by V=10k the gap is 100× the other way.

## Chunk 6 — what was actually built

| # | Deliverable | Status | Notes |
|---|---|---|---|
| A | Trivial baselines | DONE @ `7ad89c0` | zero-context + exploit-baseline. Exit gate 2 reframed as paired uplift CI vs zero-context (T=0.20). Current N=46 → Δacc=+0.20, CI=[+0.07,+0.33] → FAIL strict, PASS at T=0.45 catastrophic ceiling. See `research/exit_gate_2_priors_floor.md`. |
| B | Iso-accuracy / iso-budget | DONE @ `7ad89c0` | `iso_accuracy_tokens` + `iso_budget_accuracy` in `core.metrics`. `run_iso.py` reads `chunk3.jsonl`, prints per-V tables + 3×2 small-multiples plot. No new spend. |
| D | Trace-aware exploit detector | DONE @ `7ad89c0` | `tokenbench/audit/exploit_detector.py` + `scripts/audit_runs.py`. C1/C2/C3 active; C4 placeholder for v1.1 agent traces. Exit gate 3 PASS on `chunk6_rigor.jsonl` (0 HIGH). |
| C | Statistical rigor | DONE @ `221e1d1` | Scope F-trim, ~$50. 24 needle × 5 providers × 2 models × 3 repeats (raw-dump excluded on sonnet-4-5×needle). 30 stratified SWE-QA × 4 providers (no raw-dump) × 2 models × 3 repeats. Outputs `chunk6_rigor.{jsonl,db}` + summary md + Pareto-with-CIs plot. Handoff's $35-60 estimate was 25× too low; re-estimated to $1,260 for the literal scope, F-trim hit $50. |
| E | Held-out 80/20 split | DONE @ `f1ad5e7` | `tokenbench/datasets/splits.py` (deterministic, no seed). `scripts/freeze_splits.py` ran once: needle 240/60, SWE-QA 168/42. Public manifests tracked, held-out gitignored. |
| F | Datasheet | DONE @ `f1ad5e7` | `DATASHEET.md` follows Datasheets-for-Datasets (Gebru et al.) Q1–Q40 + addenda for calibration history, frozen configs, scoring leniencies, rotation policy. |
| H | Leaderboard + submission protocol | DONE @ `f1ad5e7` | `scripts/generate_leaderboard.py` reads any store, filters to public split, marks V=1 Pareto with ★, optional `--include-heldout` for local audit. `LEADERBOARD.md` + `SUBMISSION.md` written. |
| ~~G~~ | ~~Agentic provider~~ | DEFERRED v1.1 | `research/agentic_provider_deferred.md`. |

## Chunk 6 exit-gate state

| # | Exit gate | Status |
|---|---|---|
| 1 | Public-vs-held-out gap within noise | **scaffolding only** — gap column wired in `generate_leaderboard.py --include-heldout` but no held-out cells in any store. Need Task A. |
| 2 | Exploit baseline scores ~0 | reframed PASS at T=0.45 catastrophic ceiling, conditional FAIL at T=0.20 strict. Documented in `research/exit_gate_2_priors_floor.md`. No further runs needed unless T=0.20 certification is wanted. |
| 3 | Trace audit no harness gaming | **PASS** — `scripts/audit_runs.py --records results/runs/chunk6_rigor.jsonl` returns 0 HIGH. |
| 4 | Results stable across ≥5 repeats | **partial** — Phase 2 ran 3 repeats per scope F-trim. Spec floor is 5. Skippable with documented deviation, OR run Task B. |
| 5 | Stranger test (clean clone reproduces) | **scaffolding only** — `repro/run_cell.py` + `make repro` exist; never exercised from a fresh clone. Need Task C. |
| 6 | Pareto frontier across methods, not "Nx" | **PASS** — `LEADERBOARD.md` ★ markers, no single-N claim. |

---

## v1.0 close-out plan (NEXT — read `research/v1_0_close_out_plan.md` first)

Three remaining gates → three tasks. Plan locks scope after one user decision (L / M / XL).

| Task | What | Closes gate | Cost (recommended scope L) |
|---|---|---|---:|
| **C-local** | Stranger test on a local fresh clone (`/tmp/tokenbench-stranger`) | #5 | $0 |
| **B (skip)** | Document 3-repeat deviation in DATASHEET.md | #4 | $0 |
| **A-partial** | 30 stratified held-out SWE-QA tasks, 3 repeats, judge | #1 | ~$13 |
| | | **TOTAL** | **~$13** |

Other scopes:
- **M (~$57):** C-local + full B (5-repeat top-up on public Phase 2 scope) + A-partial.
- **XL (~$167):** C-local + full B (5-repeat over full F-trim incl held-out) + full A (all 60 needle + 42 SWE-QA held-out, 3 repeats).

### Sequencing within whichever scope (locked)

1. **C-local first.** Free, ~3 min. If it fails, every subsequent gateway dollar may land in a broken state. Cheap canary.
2. **A** (held-out sweep, partial or full). Judge calls dominate; running them in one continuous sweep keeps the audit log contiguous.
3. **B** (5-repeat top-up) if scope M or XL.
4. Regenerate `LEADERBOARD.md` with `--include-heldout` after A lands. Run `audit_runs.py`. Update `DATASHEET.md` calibration-history addendum to record actual close-out actions taken.
5. `git tag v1.0.0` on the commit that closes the last gate.

### Open decisions (the ONLY questions for the next session)

1. **Scope L / M / XL?** Recommended L (~$13).
2. **A-partial 30 vs A-full 42 SWE-QA held-out tasks?** Default 30 stratified.
3. **Skip B with datasheet note, or run it?** Default skip.

### Frozen settings carried from this session (do not relitigate)

| # | Setting | Value | Rationale |
|---|---|---|---|
| 1 | Repeats per cell (Phase 2) | **3** | F-trim scope locked. Going to 5 is Task B. |
| 2 | Bootstrap | **Task-level, average across repeats** | Standard for benchmarks. |
| 3 | Iso-accuracy targets | **50% / 70% / 90%** | Three points show curve shape. |
| 4 | Iso-budget targets | **1k / 10k / 100k tokens** | Mirrors V ∈ {1, 100, 10k}. |
| 5 | Agentic provider (G) | **Defer to v1.1** | Saves $50-200; v1.0 already publishable. |
| 6 | Public release | **Local only at v1.0** | GitHub push from a second device after v1.0 hardens. |
| 7 | Datasheet template | **Gebru et al. Datasheets for Datasets** | Locked 2026-06-14. Ships as `DATASHEET.md`. |
| 8 | Phase 2 SWE-QA judge run id | `chunk6-smoke` | Sticky audit log; reuse on resume. |

## Important runtime/behaviour notes (carried)

1. **`Runner.sweep()` skips already-recorded cells.** Returned list contains only newly-executed cells. Read `store.all()` filtered by selection, not the sweep return value, or summary tables print empty after a resumed run.
2. **`provider.build(task)` is memoised per `(provider, task)` per sweep.**
3. **`freeform_prompt()` in `prompt_wrapper.py`** has the same structural shape as `standard_prompt()` so context-token counts stay comparable across needle and SWE-QA.
4. **`LLMJudge` HARD FAILS at construction if judge_model.name is `bedrock.anthropic.claude-sonnet-4-5` or `openai.gpt-4o-mini`** — DECISIONS.md #9.
5. **Held-out manifests live under `artifacts/_heldout/` which is gitignored.** Never commit a held-out file. The split is byte-identical re-runnable from `freeze_splits.py` against the v1.0 task lists.
6. **Cell key includes `(task_id, provider_name, provider_version, model, repeat, seed, dataset_version, harness_version)`.** Idempotent skip is keyed on this tuple; resuming a kill mid-sweep is safe. Bumping `provider.version` is how a method gets re-scored after a config change.
7. **Phase 2 sweep "smoke run" salvage:** the first run wrote 169 records under `chunk6_rigor_smoke.jsonl` before the SWE-QA limit was clamped; those records are byte-key compatible with the real run's repeat=0 and were promoted into `chunk6_rigor.jsonl` to avoid re-spend. Don't be confused by the smoke filename in any audit-log artefacts (`results/judge/chunk6-smoke.jsonl`).

## Practical notes for the v1.0 close-out agent

1. **Phase 1+2+3 of Chunk 6 are all DONE.** The remaining work is exit-gate verification, not feature build. Read `research/v1_0_close_out_plan.md` first; that's the contract.
2. **Don't break Chunk 3 numbers.** Spot-check after any change to runner/judges/providers: `python run_chunk3.py --tasks-per-repo 1 --repeats 1 --providers rag-bm25 --models bedrock.anthropic.claude-sonnet-4-5`. ~$0.0001 thanks to idempotent skip.
3. **User prefers concise updates, no narration.** Tool calls speak for themselves; one-sentence text between groups; end-of-turn summary in two sentences max.
4. **Cumulative spend tracker:** ~$65 through end of Chunk 6 Phase 3. Scope L close-out adds ~$13 → total v1.0 budget ~$80.
5. **`JUDGE_RUBRIC_VERSION = 1.1.0`** is the canonical rubric. v1.0.0 calibration numbers retained for transparency in `results/judge/calibration_judge-5f2c4466.json` — DATASHEET.md discloses both.
6. **The held-out re-sweep (Task A) reuses `run_chunk6_rigor.py`.** Two paths:
   - Add a `--questions-path` flag so the SWE-QA pass can point at a held-out subset file built by re-running `sample_swe_qa.py` against the held-out manifest.
   - Or filter the existing dataset at runtime by intersecting with the held-out manifest. Cleaner: build a `HeldoutSweQaDataset` wrapper.
7. **The "stranger test" (Task C) walks the existing `repro/Makefile`.** No new code needed — invoke `make repro TASK=needle-click-0000` from a fresh clone, capture the RunRecord, compare `telemetry.input_tokens_norm` against the LEADERBOARD.md value. Record the result in a new `repro/STRANGER_LOG.md`.
8. **Test count:** 146 passing as of `f1ad5e7`. Any close-out task that adds code should add tests; gate-verification tasks may not require any.
9. **Audit before publication:** `python scripts/audit_runs.py --records results/runs/chunk6_rigor.jsonl` must return exit code 0 (no HIGH findings) before any tag is cut. Currently passing.

## Resume checklist (for fresh Claude window)

```bash
cd "/Users/hgupta163/dev/Token Efficinecy Benchmark"
source .venv/bin/activate
git log --oneline | head -6                                  # confirm f1ad5e7 + 221e1d1 + 7ad89c0 + 757d65b visible
pytest -q                                                     # 146 passing
python scripts/verify_snapshot.py                             # all 3 snapshots ok
ls results/runs/chunk6_rigor.jsonl                           # 1,386 records
ls artifacts/swe_qa/v1.0.0/sample_chunk6.jsonl               # 30 stratified rigor-sweep tasks
ls artifacts/swe_qa/v1.0.0/public_split.tsv                  # 168 SWE-QA public ids
ls artifacts/needle/v1.0.0/public_split.tsv                  # 240 needle public ids
ls artifacts/_heldout/swe_qa/v1.0.0/heldout_split.tsv        # 42 held-out SWE-QA ids (gitignored)
ls DATASHEET.md LEADERBOARD.md SUBMISSION.md                 # release-surface docs
python scripts/audit_runs.py --records results/runs/chunk6_rigor.jsonl   # must say "Audit clean"
```

Then:
1. Read `research/v1_0_close_out_plan.md` for the three-task plan.
2. Read this file (you already are) and `DATASHEET.md` for the project's known-limitations posture.
3. Ask the three open questions (scope L/M/XL, A-partial 30 vs A-full 42, run-or-skip B). Default L / 30 / skip.
4. Sequence: **C-local first** ($0 canary) → **A** (held-out sweep) → optionally **B** (5-repeat top-up).
5. After all gates pass, regenerate `LEADERBOARD.md --include-heldout`, update `DATASHEET.md` calibration-history addendum, run `audit_runs.py`, then `git tag v1.0.0`.
6. The v1.1 backlog is in `research/agentic_provider_deferred.md`. Don't pull from it until v1.0 is tagged.

---

**Status as of v1.0 close-out kickoff:** Chunks 1–6 complete bar exit-gate verification. 146/146 tests green. `dataset_version: 1.0.0`, `harness_version: 0.1.0`, `JUDGE_RUBRIC_VERSION: 1.1.0`. Cumulative gateway spend: ~$65. All decisions locked. SWE-QA leaderboard: rag-bm25×sonnet-4-5 leads at 0.622 [0.46, 0.79]. Three exit gates remain (#1, #4, #5); plan recommends scope L (~$13). Ready to start with the C-local stranger test.
