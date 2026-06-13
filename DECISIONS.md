# TokenBench — Locked Decisions

Per `tokenbench_architecture.md` §5, these decisions are expensive to retrofit and must be locked before code is written. Switching any of them mid-stream invalidates prior comparisons and forces a new `dataset_version`.

This file is the source of truth. Every chunk references it.

---

## 1. Reference tokenizer

**Locked: `o200k_base`** (via `tiktoken.get_encoding("o200k_base")`).

All token counts reported in `*_norm` fields use this encoder. Native counts from each provider's usage API are stored separately in `native_*` fields for billing-dashboard cross-checks.

**Why locked:** changing the tokenizer invalidates every token count ever recorded. (§5 #1)

---

## 2. Public vs held-out split policy

**Locked: 80% public / 20% held-out**, stratified by language and repo size.

- **Public split:** anyone can run, leaderboard accepts submissions.
- **Held-out split:** kept private, used to detect contamination (a method scoring much better on public than held-out is overfit or contaminated).
- The held-out split is **never** distributed with the dataset release.
- Tasks are assigned to splits at `dataset_version` freeze and never re-assigned.

**Why locked:** you cannot un-publish a held-out set. (§5 #2)

---

## 3. Isolation boundary

**Locked: scoring runs outside the agent's container; gold answers never enter the agent's context.**

- Provider plugins run in the agent container (control plane).
- Scoring service runs in a separate process / container (evaluation plane).
- Gold answers (`task.gold`, `task.needle`) are loaded only by the scoring service and never passed to the provider or model.
- Run records are written to the immutable Results Store, which the agent container has no write access to.

**Why locked:** UC Berkeley RDI showed 8 major agent benchmarks could be driven to ~100% by an agent that reached across this boundary. Bolting it on later is a rewrite. (§5 #3)

---

## 4. Run-record immutability

**Locked: append-only from the first real run.**

- Run records are versioned by `(dataset_version, harness_version, provider_version, model)`.
- Once written, a record is never modified — only superseded by a new record with a new `run_id`.
- Storage: SQLite (local) + JSONL append log + Parquet exports (Chunk 4+).

**Why locked:** without immutability you cannot regenerate or audit the leaderboard. (§5 #4)

---

## 5. Build-cost amortization

**Locked: report TPCA at V ∈ {1, 100, 10000}.**

- A single TPCA number without a stated V is **forbidden** for any method with non-zero build cost (Graphify, RAG indexes, repo-map).
- The amortization curve (TPCA vs V on log-x) is mandatory in every method comparison.
- The accuracy-vs-tokens **Pareto frontier** is the headline visual; TPCA(V) is the headline number at the chosen V.

**Why locked:** Graphify's claim depends entirely on V. At V=1 (cold start) it may look terrible; at V=10k (warm) it may dominate. Reporting only one V is a load-bearing lie. (§0.1, §5 #5)

---

## 6. Method-fairness protocol

**Locked: FROZEN PUBLISHED CONFIGS.**

For each provider, we use the configuration published by the method's authors as of the `dataset_version` freeze date. Configurations are recorded as `(commit_sha, config_file_path)` and stored in `tokenbench/providers/<name>/frozen_config.yaml`. **Tuning during scoring is forbidden.**

**Rationale:** keeps tuning effort from confounding method comparison and reflects how a typical user encounters the method. Costs equal-budget fairness; mitigated by reporting upstream config provenance with every result.

**Switching to equal-budget tuning would require a new `dataset_version`.**

See `research/method_fairness_and_model_adapters.md` for the long-form rationale.

**Why locked:** "frozen" vs "equal-budget" produces different leaderboards on the same data. Switching mid-stream invalidates prior comparisons. (§5 #6)

---

## 7. Held-out rotation policy

**Locked:**
- **Cadence:** rotate the held-out split every 12 months by default.
- **Early-rotation triggers:**
  - Public-vs-held-out gap exceeds 2× bootstrap CI for any submitted method (suspected contamination)
  - Any task in the held-out split is publicly leaked
  - Canary string for the dataset version appears in any model's training corpus disclosure
- **What happens to past leaderboard entries:** archived under `dataset_version: <old>` with a `superseded_by: <new>` pointer. Old entries are never deleted; they remain queryable but are not displayed on the active leaderboard.

**Why locked:** SWE-bench Verified was retired in 2026 partly because rotation policy was not pinned up front. (§5 #7)

---

## 8. Model adapter architecture (additional lock)

**Locked: all model providers conform to `tokenbench.models.base.Model`.**

Adapters must:
- Capture native tokens from the provider's usage API
- Re-count input + output in `o200k_base` via `tiktoken`
- Record latency in milliseconds
- Log full request + response to `trace_uri`

Adapters live in `tokenbench/models/<provider>.py`. Adding a provider requires only a new adapter file conforming to the `Model` ABC — no other code changes.

**First adapter:** Anthropic (Chunk 2). Additional providers added as needed in later chunks.

See `research/method_fairness_and_model_adapters.md` for the rationale.

---

## 9. LLM judge model

**Locked: `bedrock.anthropic.claude-opus-4-7`.**

The judge model used by `tokenbench.judges.llm_judge.LLMJudge` for free-form
SWE-QA scoring. Must differ from any answering model used in the same sweep
(currently sonnet-4-5 and gpt-4o-mini) to avoid exact-model self-preference
bias.

Within-family bias risk (opus-4-7 judging sonnet-4-5 outputs) is mitigated by:
- Anonymized + shuffled inputs (§Chunk 5 deliverable 2)
- A 20-task robustness spot-check on `openai.gpt-4o`; verdicts must agree on
  ≥17/20 (binomial p<0.001 vs 50/50) or the judge is recused

**Why locked:** the judge is part of the measurement instrument; switching it
mid-stream invalidates κ calibration and forces a new `harness_version`.
(§5 #4, Chunk 5 exit gate 3)

---

## 10. SWE-QA source

**Locked: hand-curated from `artifacts/repos/{click,rich,httpx}/` at the pinned
SHAs of `dataset_version: 1.0.0`.**

≥200 free-form questions, written by the dataset author against the same
pinned snapshots used for needle-codebase. Public benchmarks (SWE-bench,
RepoQA) are **excluded** because gateway models have very likely trained on
them, which would contaminate the accuracy measurement.

**Why locked:** changing source after release would mean a new dataset, not a
new version. (§5 #2)

---

## 11. Human gold set production

**Locked: single annotator (dataset author), ≥200 labels, with test-retest
sub-sample.**

- 200 SWE-QA tasks labeled pass/fail by the dataset author
- 20 of those double-labeled with a ≥48-hour gap for within-rater
  test-retest κ (proxy for label stability since we have no second annotator)
- Every label written with `annotator_id` and ISO-8601 timestamp
- Labels committed to git **before** any judge run (verified by `git log` —
  Chunk 5 exit gate 4)
- **No relabeling after seeing judge outputs.** Period. That is p-hacking
  and pre-registered as forbidden.

If a future second annotator is added, their labels go into a separate file
under a new dataset_version; the original gold set is never edited.

**Why locked:** label provenance is the foundation of κ. (§5 #4, Chunk 5 ex. gate 4)

---

## 12. ECE threshold

**Locked: primary ECE ≤ 0.10. "Well-calibrated" badge ECE ≤ 0.05.**

Expected Calibration Error of the LLM judge against the human gold set,
computed by `scripts/calibrate_judge.py`.

- **ECE > 0.10:** judge fails calibration; SWE-QA flagged exploratory in all
  reports; headline TPCA continues to use auto-scored datasets only.
- **0.05 < ECE ≤ 0.10:** judge passes; SWE-QA may join headline numbers.
- **ECE ≤ 0.05:** judge earns "well-calibrated" badge in run records.

Bin count: 10 equal-width bins over the judge's confidence
(majority-vote share, so confidence ∈ {2/3, 1.0} for N=3).

**Why locked:** the calibration threshold must be set before judge results are
seen. Picking it after = p-hacking. (Chunk 5 exit gate 2)

---

## Change log

This file is append-only. Decisions are not edited; they are superseded by new entries with a new `dataset_version`.

| Date | Decision changed | Old → New | New `dataset_version` |
|---|---|---|---|
| 2026-06-09 | Initial freeze | — | 1.0.0 |
| 2026-06-10 | +Decisions 9–12 (judge model, SWE-QA source, gold set plan, ECE threshold) | — | 1.0.0 (additive — judge is harness-versioned, not dataset-versioned) |
| 2026-06-13 | Judge rubric pass-floor for `faithfulness` dim relaxed | `==2` → `≥1` | 1.0.0 (`JUDGE_RUBRIC_VERSION` bumped 1.0.0 → 1.1.0; rubric is harness-versioned, not dataset-versioned) |

### 2026-06-13 — rubric v1.1.0: relax `faithfulness` floor

**What changed:** `PASS_FLOOR["faithfulness"]` lowered from `==2` to `≥1` in
`tokenbench/judges/llm_judge.py`. `JUDGE_RUBRIC_VERSION` bumped 1.0.0 → 1.1.0.
Other floors unchanged: `correctness ≥ 1`, `completeness ≥ 1`.

**Why:** The first calibration run (`results/judge/calibration_judge-5f2c4466.json`,
opus-4-7, N=3, n=210) failed the primary ECE threshold:
- κ = 0.609 (✅ ≥ 0.60)
- ECE = 0.200 (❌ ≤ 0.10)

Per-dimension diagnostics on the saved vote dims (see `scripts/diagnose_ece.py`)
showed:

| Dim | Mean when human=PASS | Mean when human=FAIL | Floor | Discriminating? |
|---|---:|---:|---|---|
| correctness | 1.64 | 0.51 | ≥1 | yes (gap = 1.13) |
| completeness | 1.06 | 0.09 | ≥1 | yes (gap = 0.97) |
| **faithfulness** | **1.73** | **1.66** | **==2** | **no (gap = 0.07)** |

`faithfulness` did not separate human-pass from human-fail answers (means
overlap by 0.07 vs 0.97–1.13 on the other dims) but the strict `==2` floor
drove the false-negative rate to 30% (37/122 human-pass tasks were marked fail
by the judge solely because faithfulness landed at 1, not 2).

Counterfactual recomputation from saved vote dims (no new judge calls):

| Floor (corr/comp/faith) | κ | ECE | Verdict |
|---|---:|---:|---|
| 1/1/2 (v1.0.0, current) | 0.609 | 0.200 | κ ✅, ECE ❌ |
| **1/1/1 (v1.1.0, new)** | **0.806** | **0.092** | **✅ both pass** |

**Integrity rationale:** This is a measurement-validity correction, not a
threshold-shop. The data shows the dim does not discriminate; relaxing its
floor is the principled fix. Both numbers (v1.0.0 and v1.1.0) will be
disclosed in the datasheet (Chunk 6 deliverable F). The rubric prompt itself
is unchanged — only the binary aggregation rule over the saved vote dims.
Human labels are not relabeled.

**Effect:** SWE-QA can now enter headline TPCA in Chunk 6 (κ ≥ 0.6 and
ECE ≤ 0.10 both satisfied under rubric v1.1.0). Audit log
`results/judge/judge-5f2c4466.jsonl` and full v1.0.0 calibration report retained
unchanged for transparency.
