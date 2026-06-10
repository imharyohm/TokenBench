# Building a Codebase-Context Token-Efficiency Benchmark
### Reference architecture + development pathway, modelled on how modern benchmarks are actually engineered

---

## 0. Framing: a benchmark is a measurement instrument, not a script

The mistake most homegrown benchmarks make is treating the scoring loop as the
product. In modern practice (SWE-bench, HELM, GAIA, BIG-bench, τ-bench, HAL),
the scoring loop is maybe 10% of the work. A benchmark is a *measurement
instrument*, and instruments are judged on three properties:

- **Validity** — does it measure the thing you claim (token efficiency of a
  context method), and not a confound (the agent loop, the tokenizer, training
  contamination)?
- **Reliability** — does it give the same answer on repeats, and are differences
  between methods statistically real rather than noise?
- **Governance** — is it versioned, contamination-resistant, reproducible by a
  stranger, and maintainable as models change?

Everything below is organised so that each layer defends one of these.

The modern benchmark lifecycle has eight stages. The rest of this doc is that
lifecycle, instantiated for your problem.

```
  ① Construct      ② Data curation     ③ Task schema      ④ Execution
     definition   →   + contamination →   + environments →   harness
                                                                  │
  ⑧ Maintenance   ⑦ Release           ⑥ Metrics          ⑤ Scoring
     + versioning ←   + governance    ←   + aggregation   ←   + calibration
```

### 0.1 The primary metric (TPCA), formally

For a method *m* on task set *T* with *R* repeats per task:

    TPCA(m, V) = ( Σ_{t∈T} Σ_{r=1..R} tokens(m, t, r, V) )
               / ( Σ_{t∈T} Σ_{r=1..R} 1{correct(m, t, r)} )

where  `tokens(m, t, r, V) = input_norm + output_norm + (build_norm / V)`.

*V* is the **amortization volume** — the number of queries the one-time
build cost is spread over. **A single TPCA number without a stated V is
forbidden** for methods with non-zero build cost (Graphify, RAG indexes);
report curves at V ∈ {1, 100, 10000}. The accuracy-vs-tokens **Pareto
frontier** is the headline visual; TPCA(V) is the headline number at the
chosen V.

Correctness is binary per attempt; on free-form QA the LLM-judge's
pass/fail decision (not a fractional score) keeps the denominator
interpretable as "answers." Report TPCA's distribution (median + IQR), not
just the mean — token usage is heavy-tailed.

---

## 1. Reference architecture (the system)

Eleven components. The dotted line is the **isolation boundary** — the single
most important design decision (UC Berkeley RDI showed 8 major agent benchmarks
could be driven to ~100% by an agent that reached across this boundary and
exploited the evaluator instead of solving tasks).

```
┌─────────────────────────────────────────────────────────────────────┐
│  CONTROL PLANE                                                        │
│                                                                       │
│  [1] Task Registry        [2] Artifact / Env Store                    │
│      versioned tasks          pinned repo snapshots @ commit          │
│      (JSON schema)            Docker image per task                   │
│         │                         │                                   │
│         ▼                         ▼                                   │
│  [5] Execution Engine (Runner) ───────────────────────────────────┐  │
│      seeded · idempotent · parallel · N repeats per cell           │  │
│         │                                                          │  │
│         │  injects ONE controlled variable:                        │  │
│         ▼                                                          │  │
│  [3] Provider Plugins  ──►  [4] Model Adapters                     │  │
│      raw / rag / graphify    answering LLM(s)                      │  │
│      repo-map / llmlingua    usage telemetry from API              │  │
│         │                         │                                │  │
│         └─────────► [6] Telemetry Bus ◄────────────────────────────┘  │
│                         tokens: input/output/cache/build              │
│                         normalized (o200k_base) + native              │
│                         + full trace/log capture                      │
│                              │                                        │
└──────────────────────────────┼───────────────────────────────────────┘
            ISOLATION BOUNDARY  │   (scoring NEVER runs in agent's env;
- - - - - - - - - - - - - - - - ┼ - gold answers NEVER enter agent context)
┌──────────────────────────────┼───────────────────────────────────────┐
│  EVALUATION PLANE             ▼                                        │
│                                                                       │
│  [7] Scoring Service        [8] Metrics & Aggregation                 │
│      auto (RepoQA, tests)       TPCA · E0 · compression · Pareto       │
│      LLM-judge (calibrated)     bootstrap CIs · variance              │
│         │                         │                                   │
│         ▼                         ▼                                   │
│  [9] Results Store ──────►  [10] Leaderboard / Reporting              │
│      immutable run records       public split + held-out split        │
│      (versioned, queryable)      datasheet + reproducibility pkg      │
│                                                                       │
│  [11] Governance: versioning · split policy · contamination refresh   │
└───────────────────────────────────────────────────────────────────────┘
```

### Component responsibilities

**[1] Task Registry.** Every task is a versioned, machine-readable record (schema
in §4). Tasks carry a `dataset_version` and `canary` field. This is what makes
results comparable across time and reproducible by others.

**[2] Artifact / Environment Store.** The thing SWE-bench got right: each task
pins a repository at an exact commit and (ideally) ships a Docker image so the
environment is deterministic. For a *context* benchmark you need the repo
snapshot reproducible to the byte, because token counts depend on exact file
contents. Store snapshots immutably (content-addressed, e.g. by git SHA + tarball
hash).

**[3] Provider Plugins — the controlled variable.** Each context method
(raw dump, RAG, Graphify, repo-map, LLMLingua-2) is a plugin behind one
interface. This is the *only* thing that changes between runs. Everything else
is frozen. This is what buys you validity: differences in the result are
attributable to the method.

**[4] Model Adapters.** Provider-agnostic answering models. Adapters pull
**token usage from the provider's usage API** (ground truth) and re-count in the
reference tokenizer for fair cross-model comparison.

**[5] Execution Engine (Runner).** Orchestrates `tasks × providers × models ×
repeats`. Must be: *seeded* (reproducible), *idempotent* (re-running a cell
gives the same record or is skipped), *parallel* (you'll run tens of thousands
of cells — HAL ran 21,730 rollouts), and *resumable* (checkpoint after each
cell; never lose a $40k run to a crash).

**[6] Telemetry Bus.** Captures, per attempt: input / output / cache / one-time
build tokens, both normalized and native; latency; and the **full trace** (every
tool call, every file read). Traces are non-negotiable now — outcome-only scoring
can't tell "solved" from "exploited the harness" or "recalled from training."

**[7] Scoring Service — across the isolation boundary.** Runs *outside* the
agent's container. Automatic scorers (RepoQA needle-containment, unit tests)
where possible; calibrated LLM-judge for free-form QA. Gold answers live here and
never cross into the agent's environment.

**[8] Metrics & Aggregation.** Computes TPCA, E0, compression ratio, accuracy,
and the accuracy-vs-tokens Pareto frontier, with bootstrap CIs over tasks and
repeats. Reports distributions, not means (token usage is heavy-tailed).

**[9] Results Store.** Immutable, append-only run records, versioned by
`(dataset_version, harness_version, provider_version, model)`. This is your
audit trail and what regenerates the leaderboard.

**[10] Leaderboard / Reporting.** Two splits: a **public** split anyone can run,
and a **held-out** split you keep private to detect contamination (a method that
does suspiciously better on public than held-out is overfit or contaminated).
Ship a **datasheet** (provenance, licensing, known limitations) — this is now
standard practice (Datasheets for Datasets, Gebru et al.).

**[11] Governance.** Versioning policy, split-rotation cadence, and a
contamination-refresh schedule. SWE-bench Verified was *retired* in 2026 once
contamination set in; design for that from day one.

---

## 2. The validity chain (what each layer is defending)

| Threat | Where it's defended | Concrete mechanism |
|---|---|---|
| Confound: agent loop, not method | [3] Provider isolation; single-shot Layer-1 tasks | Hold model+task fixed; swap only the provider |
| Confound: tokenizer differences | [4][6] Reference-tokenizer normalization | Re-count everything in o200k_base |
| Confound: prompt-format / position bias | [3] Standardized provider wrapper | Common system + question template across providers; ablate format on a sample |
| Confound: tuning effort, not method | [3][11] Method-fairness protocol | Each provider tuned with equal budget on a fixed dev split, OR frozen at the method's published config; declare which |
| Contamination (repo in training data) | [1][2][10][11] Held-out split, fresh data, refresh cadence | Canary strings; public/held-out gap check; rotate on a pre-committed schedule |
| Harness gaming | Isolation boundary; [7] separated scorer; trace audit | Score outside agent container; gold never in-context; flag traces that read gold-answer files outside the provider's returned context |
| Noise / instability | [5][8] Repeats + CIs + power calc | N≥5 repeats; bootstrap; report median+IQR; pre-compute task count needed to detect a 20% TPCA delta at α=0.05 |
| Judge unreliability | [7] Calibration | ≥200-example human gold set; pre-registered κ ≥ 0.6 threshold; report κ + ECE; auto-score where possible |
| Irreproducibility | [2][9] Pinned envs + immutable records | Docker per task; content-addressed snapshots |

If you can point to a defense for every row, you have a publishable benchmark.
If any row is undefended, that's where a reviewer (or reality) breaks you.

---

## 3. Development pathway (phases with gates)

Each phase has an **entry gate**, **deliverable**, and an **exit gate** (the
validity/reliability check that must pass before moving on). This is the
discipline that separates a benchmark from a demo.

### P0 — Construct definition (paper, not code)
- **Deliverable:** a one-page spec answering: *exactly* what capability is
  measured ("correct answers per normalized token, attributable to context
  method"); the task taxonomy; the primary metric (TPCA, formula in §0.1, with
  a chosen default amortization volume V); the confounds and how each is
  controlled; the baselines (including a *trivial* baseline and an *exploit*
  baseline to detect gaming); the **method-fairness protocol** (frozen configs
  vs. equal tuning budget); a **statistical power calc** that fixes |T| and R
  to detect a target TPCA delta at α=0.05; and a **draft datasheet**
  (provenance, licensing, intended/out-of-scope use) — written *now*, not at
  release, so collection decisions are made with those questions in mind.
- **Exit gate:** a skeptical colleague agrees the metric can't be trivially
  gamed and measures the claimed thing; the power calc shows the planned
  dataset size is sufficient, not aspirational.

### P1 — Skeleton + offline mock  *(done — your tokenbench scaffold)*
- **Deliverable:** Provider/Model/Dataset/Judge/Runner running end-to-end with
  mocks; metric math unit-tested.
- **Exit gate:** `run_demo.py` produces a Pareto frontier; metrics pass self-tests.

### P2 — First real signal (the easy, clean combo)
- **Entry:** P1 passed.
- **Deliverable:** RepoQA dataset loader + RAG provider + real model adapter with
  usage-API telemetry + reference-tokenizer normalization. RepoQA's automatic
  scorer means **zero judge risk** on day one.
- **Exit gate:** numbers reproduce across two independent runs within CI;
  token counts match the provider's billing dashboard to within a few %.

### P3 — Provider expansion
- **Deliverable:** Graphify, Aider repo-map, LLMLingua-2 behind the same
  interface. One-time build cost tracked separately and amortized per the §0.1
  TPCA(V) policy (cold V=1, warm V=100, steady V=10k). All providers share a
  standardized prompt wrapper (system + question template) so format isn't a
  confound. Method-fairness protocol from P0 applied: each provider tuned with
  the declared budget on the dev split *only*; configs frozen before scoring.
  **Cumulative cost ceiling:** before kicking off the full sweep, project
  tasks × providers × models × repeats against the per-cell token budget; if
  it exceeds the phase budget, cut breadth (fewer models) before depth (fewer
  repeats).
- **Exit gate:** swapping a provider changes *only* token/accuracy, with the
  task and model byte-identical; build-cost amortization curve plotted at all
  three V values; tuning logs archived with the run records.

### P4 — Environment + reproducibility hardening
- **Deliverable:** pinned repo snapshots (commit + hash), Docker per task,
  seeded/idempotent/resumable Runner, immutable Results Store.
- **Exit gate:** a teammate reproduces a result from a clean checkout using only
  the repro package.

### P5 — Free-form QA layer + judge calibration
- **Deliverable:** SWE-QA loader + LLM-judge (separated judge model, multi-
  dimension rubric, N× majority vote, shuffled/anonymized candidates).
  Calibrate against a **≥200-example human gold set** (30 is too few for a
  stable κ estimate). The κ threshold is **pre-registered** in P0 — do not
  relabel after seeing judge results.
- **Exit gate:** judge–human agreement κ ≥ 0.6 and ECE acceptable; otherwise
  fall back to auto-scored datasets for the headline number and report
  free-form results as exploratory only.

### P6 — Realism layer + rigor + release
- **Deliverable:** SWE-bench Pro agentic provider (telemetry only); both
  iso-accuracy and iso-budget sweeps; ≥5 repeats with bootstrap CIs and the
  task count fixed by the P0 power calc; held-out split with a
  **pre-committed rotation cadence** and a documented policy for what happens
  to past leaderboard entries on rotation; **trace-aware exploit detector**
  (flag runs whose tool calls touched gold-answer files outside the provider's
  returned context); datasheet finalized from the P0 draft; public
  leaderboard + submission protocol.
- **Exit gate:** public-vs-held-out gap within noise (no contamination
  signal); exploit baseline scores ~0; trace audit shows no harness gaming on
  the top-N submissions; results stable across repeats within the
  pre-computed CI width.

```
P0 spec ─► P1 skeleton ─► P2 clean signal ─► P3 providers ─►
P4 reproducibility ─► P5 QA+judge ─► P6 realism+release
   (validity)          (signal)        (coverage)
                     (reliability)    (governance)
```

The ordering is deliberate: **cleanest controlled measurement first**
(single-shot QA + automatic scoring), expanding outward to messier-but-more-
realistic settings (free-form QA, then agentic), trusting each new layer only
after its gate passes.

---

## 4. Schemas (make these concrete early)

A versioned task schema is what makes a benchmark a benchmark. Freeze it in P0.

### Task schema
```json
{
  "task_id": "repoqa-py-django-0007",
  "dataset_version": "1.0.0",
  "task_type": "needle_function | repo_qa | patch",
  "question": "Which function validates the session token?",
  "repo": {
    "url": "https://github.com/...",
    "commit": "a1b2c3d...",
    "snapshot_sha256": "deadbeef...",
    "docker_image": "tokenbench/repoqa-django-0007:1.0.0"
  },
  "gold": "validate_session_token",
  "needle": "validate_session_token",
  "scoring": "auto_contains | unit_test | llm_judge",
  "canary": "TOKENBENCH-CANARY-uuid",
  "license": "BSD-3-Clause",
  "meta": { "language": "python", "repo_loc": 312000 }
}
```

### Run-record schema (immutable, one per cell)
```json
{
  "run_id": "uuid",
  "task_id": "repoqa-py-django-0007",
  "dataset_version": "1.0.0",
  "harness_version": "0.3.1",
  "provider": { "name": "graphify", "version": "3.0.0", "config": {...} },
  "model": "claude-sonnet-4-5",
  "repeat": 2,
  "seed": 42,
  "telemetry": {
    "input_tokens_norm": 1701, "output_tokens_norm": 48,
    "cache_tokens_norm": 0,    "build_tokens_norm": 40000,
    "native_input": 1655, "native_output": 47,
    "latency_ms": 2210, "trace_uri": "s3://.../trace.jsonl"
  },
  "score": { "correct": true, "raw": 1.0, "scorer": "auto_contains" },
  "timestamp": "2026-..."
}
```

The `canary` field (a unique uninstructed string per dataset) is how you later
test whether a model was trained on your benchmark — if it can reproduce the
canary, it's contaminated. This is standard since BIG-bench.

---

## 5. Decisions that are expensive to change later

Lock these in P0/P4 — retrofitting them is painful:

1. **Reference tokenizer.** Pick one (o200k_base) and normalize *everything* to
   it. Changing this later invalidates all prior results.
2. **Public vs held-out split policy.** Decide the ratio and what stays private
   *before* you collect data. You can't un-publish a held-out set.
3. **Isolation boundary.** Scoring outside the agent container, gold never
   in-context. Bolting this on after an agentic harness exists is a rewrite.
4. **Immutable, versioned run records.** Append-only from the first real run, or
   you lose the ability to regenerate/audit the leaderboard.
5. **Build-cost accounting.** Decide how one-time index/graph build cost is
   amortized and reported (see §0.1: report TPCA at V ∈ {1, 100, 10000}). It's
   the difference between Graphify looking great (warm, many queries) and
   terrible (cold, two queries).
6. **Method-fairness protocol.** "Frozen published configs" vs. "equal tuning
   budget on a dev split" produces different leaderboards. Pick one in P0;
   switching mid-stream invalidates prior comparisons.
7. **Held-out rotation policy.** Cadence, the trigger for rotating early
   (e.g., suspected contamination), and what becomes of past leaderboard
   entries when you rotate. SWE-bench Verified was retired in 2026 partly
   because this wasn't pinned down up front.

---

## 6. What "done" looks like

A stranger can: clone the repo, `pip install`, pull a pinned task environment,
run any (provider × model) cell, get token + accuracy numbers that match your
published CIs, and see *why* via the trace. The leaderboard shows an accuracy-vs-
normalized-token Pareto frontier across methods, the held-out split agrees with
the public split, and a trivial exploit agent scores zero. At that point you're
not claiming "71.5×" — you're publishing the curve that tells anyone which method
is genuinely efficient for their query volume and accuracy bar.
