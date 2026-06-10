# Statistical Power Calculation

> Required by P0 exit gate (§3): the planned dataset size must be sufficient to detect a target TPCA delta at α=0.05, not aspirational.

## What we are detecting

A meaningful difference between two context methods (e.g. Graphify vs RAG) on the primary metric **TPCA(V)** at the chosen amortization volume V.

- **Effect size we want to detect:** 20% relative difference in TPCA between two methods.
- **Significance level:** α = 0.05 (two-sided).
- **Statistical power:** 1 − β = 0.80 (standard).
- **Test:** paired bootstrap on per-task TPCA (paired because the same tasks are run by every method).

## Why bootstrap, not a t-test

TPCA is heavy-tailed (token counts are heavy-tailed; correctness is binary). A normal-theory t-test on the mean is the wrong instrument. We use:

1. Per-task TPCA: `tokens(method, task) / max(1, correct_count(method, task))` averaged over R repeats.
2. Paired difference per task: `Δ(task) = TPCA_A(task) − TPCA_B(task)`.
3. Bootstrap-resample tasks (with replacement) 10,000 times; compute the 95% CI of the mean Δ.
4. Significant if the CI excludes zero.

## Assumed variance

Until we have real measurements, we use these working assumptions, calibrated to RepoQA-style tasks with ~1k–10k token contexts:

- Per-task TPCA standard deviation across tasks: σ ≈ 0.5 × mean(TPCA) (heavy-tail rule of thumb)
- Within-task TPCA variance across R=5 repeats: σ_repeat ≈ 0.1 × mean(TPCA) (mostly model sampling noise)

These are **conservative** placeholders. Once Chunk 2 produces real numbers, this file will be updated and the calculation re-run before Chunk 3 expands the provider count.

## Calculation

Cohen's effect size for paired difference:

    d = Δ_target / σ_pair

where σ_pair is the standard deviation of the per-task paired difference. With both methods having σ ≈ 0.5 × μ and assuming moderate correlation ρ ≈ 0.5 between paired TPCAs (same tasks):

    σ_pair ≈ √(2 σ² (1 − ρ)) = √(2 × 0.25 × μ² × 0.5) = 0.5 × μ

For a 20% relative target (Δ = 0.2 × μ):

    d = 0.2 / 0.5 = 0.4    (small-to-medium effect)

For paired test, α=0.05 two-sided, power=0.80:

    n = ((z_{α/2} + z_β) / d)² = ((1.96 + 0.84) / 0.4)² ≈ 49 tasks

## Planned dataset sizes

| Phase | Tasks (|T|) | Repeats (R) | Effective N | Verdict |
|---|---:|---:|---:|---|
| Chunk 1 (mocks) | n/a | n/a | n/a | not measuring real signal |
| Chunk 2 (RepoQA only) | **100** | 5 | 100 | **OK** — exceeds n=49 floor with margin for the heavy tail being worse than assumed |
| Chunk 3 (multi-provider) | 100 | 5 | 100 | OK |
| Chunk 5 (+ SWE-QA) | 200 (100 RepoQA + 100 SWE-QA) | 5 | 200 | OK |
| Chunk 6 (release, with held-out) | 250 public + 50 held-out | 5 | 250 / 50 | OK on public; held-out is small but used only for contamination flagging, not for primary comparisons |

## Re-evaluation triggers

This calc is **provisional**. Re-run it when:

- Chunk 2 produces the first real TPCA distribution and we measure σ instead of assuming it.
- Any chunk's exit gate shows CI widths exceeding the pre-computed bound — that means actual variance > assumed, and |T| or R must increase.
- A new dataset is added (different domain, different variance profile).

## What this gates

If real σ is materially worse than the 0.5 × μ assumption, the |T| floor moves up. The architecture doc is explicit:

> Cumulative cost ceiling: before kicking off the full sweep, project tasks × providers × models × repeats against the per-cell token budget; **if it exceeds the phase budget, cut breadth (fewer models) before depth (fewer repeats).**

Repeats protect within-task variance. Cutting them first would be a false economy.
