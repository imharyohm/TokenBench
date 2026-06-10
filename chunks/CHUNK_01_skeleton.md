# Chunk 1 — Skeleton + Metric Math (P0/P1)

> Maps to: §3 P0 (Construct definition) + P1 (Skeleton + offline mock), §0.1 (TPCA), §4 (Schemas), §5 (Locked decisions)

## Goal
Stand up the scaffold every later chunk plugs into. **No real LLM calls.** Mocks only. Lock the expensive-to-change decisions in writing.

## Deliverables

### 1. `DECISIONS.md` — frozen choices (per §5)
Pin these BEFORE writing code:
- **Reference tokenizer:** `o200k_base` (via `tiktoken`)
- **Public/held-out split policy:** ratio + what stays private
- **Isolation boundary:** scoring runs outside agent container; gold never in-context
- **Run-record immutability:** append-only from day one
- **Build-cost amortization:** report TPCA at V ∈ {1, 100, 10000}
- **Method-fairness protocol:** "frozen published configs" OR "equal tuning budget on dev split" — pick one
- **Held-out rotation cadence:** schedule + trigger for early rotation + what happens to past entries

### 2. Repo layout
```
tokenbench/
  core/
    schemas.py           # Task + RunRecord pydantic models (§4)
    tokenizer.py         # o200k_base normalization
    metrics.py           # TPCA(V), E0, compression, Pareto
  providers/
    base.py              # Provider ABC (single controlled variable)
    mock.py              # MockProvider for P1
  models/
    base.py              # Model adapter ABC
    mock.py              # MockModel for P1
  datasets/
    base.py              # Dataset ABC
    mock.py              # MockDataset for P1
  judges/
    base.py              # Judge ABC
    auto_contains.py     # Trivial scorer for P1
  runner/
    engine.py            # tasks × providers × models × repeats
    telemetry.py         # Telemetry bus
  results/
    store.py             # Append-only run records
tests/
  test_metrics.py        # TPCA math unit tests
  test_schemas.py
  test_tokenizer.py
run_demo.py              # End-to-end mock run → Pareto plot
DECISIONS.md
power_calc.md            # |T| and R needed to detect 20% TPCA delta at α=0.05
```

### 3. Schemas (frozen in P0, §4)
- `Task` pydantic model: task_id, dataset_version, task_type, question, repo{url,commit,snapshot_sha256,docker_image}, gold, needle, scoring, canary, license, meta
- `RunRecord` pydantic model: run_id, task_id, dataset_version, harness_version, provider{name,version,config}, model, repeat, seed, telemetry{input/output/cache/build tokens norm+native, latency_ms, trace_uri}, score{correct,raw,scorer}, timestamp

### 4. Metric math with unit tests (§0.1)
- `tpca(records, V) → float` — formula: Σ tokens / Σ correct, where `tokens = input_norm + output_norm + build_norm/V`
- `tpca_curve(records) → dict[V, float]` for V ∈ {1, 100, 10000}
- `pareto_frontier(records) → list[(accuracy, tokens)]`
- Bootstrap CIs over tasks and repeats
- Median + IQR (token usage is heavy-tailed, do NOT report mean only)

### 5. Power calc (P0 exit gate)
Compute |T| and R needed to detect a 20% TPCA delta between two methods at α=0.05, power=0.8. Document the assumed variance and the resulting dataset size. **If aspirational > planned, cut scope before coding more.**

### 6. `run_demo.py`
Wires Mock{Dataset,Provider,Model,Judge} through the Runner, dumps a Pareto plot. Demonstrates the contract every later chunk extends.

## Exit gates (must all pass)
1. `pytest` green; metrics math has unit tests covering edge cases (zero correct, zero build cost, V=∞).
2. `run_demo.py` produces a Pareto frontier plot.
3. Skeptical-colleague check: TPCA can't be trivially gamed; metric measures the claimed thing.
4. Power calc shows planned |T|×R is sufficient, not aspirational.
5. `DECISIONS.md` has all 7 §5 items pinned.

## Parallelizable sub-tasks (for Chunk 1 fan-out)
These have no inter-dependencies and can run concurrently:
- **A.** `DECISIONS.md` + `power_calc.md` (writing, no code)
- **B.** `core/schemas.py` + `tests/test_schemas.py` (pydantic models from §4)
- **C.** `core/tokenizer.py` + `core/metrics.py` + `tests/test_metrics.py` (pure math)
- **D.** Mock provider/model/dataset/judge stubs + `runner/engine.py` skeleton

After A–D land, a final pass wires them through `run_demo.py`.
