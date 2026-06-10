# Chunk 5 — Free-form QA + Judge Calibration (P5)

> Maps to: §3 P5, §1[7], §2 (judge unreliability row)

## Goal
Extend beyond auto-scored RepoQA into messier free-form QA (SWE-QA). The judge must be **calibrated against humans before its outputs go into the headline number** — otherwise the metric is fiction.

## Entry gate
Chunk 4 passed: results are reproducible, runner is resumable, results store is immutable.

## Deliverables

### 1. `datasets/swe_qa.py` — SWE-QA loader
- Free-form questions about real repositories
- Gold answers are reference text, not strings to match
- Same `Task` schema as RepoQA but with `scoring: "llm_judge"`

### 2. `judges/llm_judge.py`
- **Separated judge model** — different model from the answering model (avoids self-preference bias)
- **Multi-dimension rubric** — at minimum: correctness, completeness, faithfulness (no hallucination)
- **N-way majority vote** — N ≥ 3, judge runs anonymized + shuffled
- **Anonymized inputs** — judge never sees which provider/model produced an answer
- Output: pass/fail (binary, per §0.1) + per-dimension scores for diagnostics

### 3. Human gold set (≥200 examples)
- Curate ≥200 SWE-QA tasks with human pass/fail labels
- **30 is too few for a stable κ estimate** — the doc explicitly warns against this
- Human labels recorded with annotator id and timestamp
- **κ threshold pre-registered in P0/Chunk 1** — do NOT relabel after seeing judge results (p-hacking)

### 4. Calibration harness
- `scripts/calibrate_judge.py`: runs judge on the 200-example human gold set
- Computes Cohen's κ (judge vs human) and ECE (Expected Calibration Error)
- **Pass condition: κ ≥ 0.6** (pre-registered threshold)
- **Fail behavior:** if κ < 0.6, fall back to auto-scored datasets for the headline number; SWE-QA results reported as "exploratory only" with this status flag in the run record

### 5. Judge run records
- Every judge call's prompt + response stored (trace_uri)
- Per-dimension scores stored alongside the binary pass/fail
- Used for post-hoc audits of suspected mis-scoring

## Exit gates
1. κ ≥ 0.6 against the human gold set, OR free-form QA explicitly flagged exploratory in all reports.
2. ECE within acceptable bounds (document the threshold in DECISIONS.md).
3. Judge prompt + rubric checked into the repo, versioned.
4. No relabeling of human gold after seeing judge results — verified by git log on the gold set.

## What this chunk gates
Whether SWE-QA can join the headline TPCA number, or stays in the exploratory appendix.
