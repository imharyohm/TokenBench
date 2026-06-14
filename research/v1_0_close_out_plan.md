# v1.0 close-out plan — three remaining exit gates

> Captured 2026-06-14. Scope: complete the 3 of 6 Chunk 6 exit gates that aren't yet verified, then freeze v1.0.0. Total projected spend: **~$10–$140** depending on which scope you accept; recommended path is **~$10–15** total (scope L below).

## Current exit-gate state

| # | Exit gate | Status | What's missing |
|---|---|---|---|
| 1 | Public-vs-held-out gap within noise | **scaffolding only** | Need actual scores on the held-out split. Today: 0 cells against held-out. |
| 2 | Exploit baseline scores ~0 | reframed PASS/conditional | Mean Δacc=+0.20, CI [+0.07, +0.33] at N=46. PASS at T=0.45, FAIL at T=0.20. Documented; no further runs needed unless you want T=0.20 certified. |
| 3 | Trace audit no harness gaming | **PASS** | `audit_runs.py` on chunk6_rigor.jsonl returns 0 HIGH. Done. |
| 4 | Results stable across ≥5 repeats within CI | **partial** (3 repeats) | Phase 2 ran at 3 repeats per scope F-trim. Spec floor is 5. |
| 5 | Stranger test (clean clone reproduces) | **scaffolding only** | `repro/run_cell.py` exists. Never exercised from a fresh clone. |
| 6 | Pareto frontier across methods, not "Nx" | **PASS** | LEADERBOARD.md ★ markers. Done. |

So the remaining work is gates **#1, #4, #5**.

## Three tasks, sized

### Task A — Held-out sweep (gate #1)

**What:** Re-run scope F-trim (5 providers × 2 models × 3 repeats) over the held-out split: 60 needle tasks + 42 SWE-QA tasks.

**Why this scope.** The held-out split was frozen by `freeze_splits.py` at v1.0.0 commit `f1ad5e7`. Gate #1 ("public-vs-held-out gap within noise") needs paired numbers on both splits at comparable statistical power. The Phase 2 sample was 25 public SWE-QA + 5 held-out SWE-QA (the rigor sample wasn't drawn against the split because the split didn't exist yet — chronological ordering issue). Re-sweeping the full held-out gives ~42 paired SWE-QA observations per provider×model and 60 needle, which puts CIs in the same ballpark as the public Phase 2 numbers.

**Cost projection.**

| Pass | Tasks | Repeats | Providers | Models | Answer $ | Judge $ | Subtotal |
|---|---:|---:|---:|---:|---:|---:|---:|
| needle | 60 | 3 | 5 (raw-dump on gpt-4o-mini only) | 2 | $10.54 | — | |
| swe-qa | 42 | 3 | 4 (no raw-dump) | 2 | $7.04 | $79.38 | |
| | | | | | | | **$96.96** |

The judge dominates as before. Same audit log can be reused (`--judge-run-id chunk6-smoke`); idempotent skip handles the public records that are already there.

**Gate criterion:** `gap = acc(public) − acc(heldout)` for each (provider, model). FAIL trigger per DECISIONS.md #7: `|gap| > 2 × bootstrap CI on public`. The leaderboard regen has the gap-flag column wired (`generate_leaderboard.py --include-heldout`). If any cell flags, contamination is suspected for that method/model and the rotation cadence kicks in.

**Risk note.** Held-out content is now in the answering model's prompts. That doesn't leak the *gold* (which the provider doesn't see), but it does enter the gateway/answering model's audit logs. If you ever need to claim "this content has never reached a model," the rotation policy (DECISIONS.md #7) is the right escape hatch — bump dataset_version on rotation.

### Task B — 5-repeat top-up (gate #4)

**What:** Add 2 more repeats (3 → 5) to the existing Phase 2 scope on the public split. Keep the held-out at 3 repeats unless A is also done.

**Why partial.** The literal spec says ≥5 repeats. Phase 2 dropped to 3 because the dry-run showed the 5-repeat version at $1,260 for full scope. Now that we're already at scope F-trim, going from 3→5 is incremental: same providers, same models, same task subset, just two more passes per cell.

**Cost projection.**

| Pass | Tasks | New repeats | Answer $ | Judge $ | Subtotal |
|---|---:|---:|---:|---:|---:|
| needle | 24 | 2 | $2.81 | — | |
| swe-qa | 30 | 2 | $3.35 | $37.80 | |
| | | | | | **$43.96** |

**Gate criterion:** "Results stable across ≥5 repeats within the pre-computed CI width." Concretely: rerun with 5 repeats, recompute task-level CIs, check that no provider's mean acc moves outside the 3-repeat 95% CI when 2 more repeats are added.

**Skippable?** Yes if you accept "3 repeats with documented CIs" as gate-equivalent. The Chunk 3 sweep at n=2 was already byte-identical across repeats for the 4 deterministic providers; only `repo-map` showed any cross-repeat noise (and only on a model-divergent failure mode). The CI widths from Phase 2 already reflect repeat-level variance via task-level bootstrap. **Recommendation:** record the deviation in DATASHEET.md (under "Calibration history") rather than spend another $44.

### Task C — Stranger test (gate #5)

**What:** Verify that a clean clone of the repo reproduces a published cell to within ~1% on tokens. The literal procedure:

```bash
git clone <local-or-future-github-url> /tmp/tokenbench-stranger
cd /tmp/tokenbench-stranger/repro
make repro TASK=needle-click-0000
# Compare telemetry.input_tokens_norm to LEADERBOARD.md / chunk3_findings.md
```

**Cost.** ~$0.001 — one cell on sonnet-4-5 at ~1.3k input tokens.

**The procedural snag.** The handoff says "user will push to GitHub from a second device after v1.0 is hardened." So Task C has two sub-paths:

- **C-local:** clone from a fresh path on this machine (`git clone . /tmp/tokenbench-stranger`). Verifies the harness is self-contained but not network-portable. Cheapest, fastest.
- **C-second-device:** the canonical "stranger." Requires the GitHub push to have happened. Out of scope until that push lands.

**Recommendation:** run **C-local now** for the v1.0 freeze, document the C-second-device step in `repro/README.md` as the post-push verification. The local clone catches everything except a missing-from-repo file (e.g. an env var only present in the working tree). To catch that, the local clone should be done with `git clone --depth 1` from a different directory, into a fresh path with no `.env` symlinks.

**Gate criterion:** `make repro TASK=needle-click-0000` exits 0, prints a `RunRecord` JSON, and `telemetry.input_tokens_norm` matches the published number for that task within ±1% (which equals 0% for deterministic providers and ~5 tokens for `repo-map`).

## Sequencing options

### Scope L — minimum publishable (recommended)

Do **C-local** ($0) + **B partial: skip, document** ($0) + **A partial: 30-task sample, not full held-out** (~$10–15).

Specifically: re-run on the 5 SWE-QA tasks already in `sample_chunk6.jsonl` that fell into the held-out split, and add ~25 more held-out tasks to make a stratified 30-task held-out sub-sample. That gives 30 paired observations against the Phase 2 public sample. Skip needle held-out — needle is auto-scored, the priors uplift is small, and contamination would show up on the SWE-QA side first if it shows up at all.

| Subtask | Cost |
|---|---:|
| C-local (stranger test on local clone) | $0 |
| B (skip + document) | $0 |
| A-partial (30 stratified held-out SWE-QA, 3 repeats, judge) | ~$13 |
| | **~$13** |

This closes gate #5 fully, gate #4 by documentation, and gate #1 with a meaningfully-sized but not-exhaustive held-out comparison.

### Scope M — middle path

C-local + B (5-repeat top-up on public Phase 2 scope) + A-partial as above.

| Subtask | Cost |
|---|---:|
| C-local | $0 |
| B (5-repeat top-up, public only) | ~$44 |
| A-partial (30 held-out SWE-QA) | ~$13 |
| | **~$57** |

### Scope XL — exhaustive

C-local + B (5-repeat on full F-trim scope including held-out) + A (full held-out sweep, 60+42 tasks).

| Subtask | Cost |
|---|---:|
| C-local | $0 |
| B (5-repeat on full F-trim incl held-out) | ~$70 |
| A (full held-out, 3 repeats) | ~$97 |
| | **~$167** |

## Sequencing within whichever scope

Run order regardless of scope:

1. **C-local first** (free, ~3 minutes). If it fails, every subsequent gateway dollar might land in a broken state. Cheap canary.
2. **A** (held-out sweep, partial or full). The judge calls dominate; running them in one continuous sweep keeps the audit log contiguous.
3. **B** (5-repeat top-up) if scope M or XL. Uses the existing rigor-sweep driver with `--repeats 5`; the idempotent runner skips the 3 repeats already done and only computes the new 2.
4. Regenerate `LEADERBOARD.md` with `--include-heldout` after A lands. Run `audit_runs.py`. Update DATASHEET.md addenda.

## Open decisions

1. **Which scope?** Recommend **scope L (~$13)**. Cheapest path that hits all three gates with defensible numbers.
2. **A-full vs A-partial.** A-partial uses 30 stratified held-out SWE-QA tasks; A-full uses all 42. Difference is $13 vs $58 (judge dominates). 30 tasks already gives bootstrap CIs around ±0.15 width.
3. **Skip B with a documented deviation, or run it?** Skipping is fine if the datasheet calls out "3 repeats per cell, justified by deterministic-provider behavior on Chunk 3 n=2." Running it costs $44 and tightens CIs by √(5/3)−1 ≈ 29%.
4. **Stranger-test directory location.** `/tmp/tokenbench-stranger` is fine for a one-shot. If you want it persistent for future regression, pick a path under your home dir and add it to a `repro/STRANGER_LOG.md`.

## Definition of v1.0 done after close-out

After whichever scope completes:

- All 6 Chunk 6 exit gates verified or documented as deviations in DATASHEET.md.
- LEADERBOARD.md regenerated, public-vs-held-out gap column populated (where data exists).
- DATASHEET.md updated to record actual close-out actions taken.
- `git tag v1.0.0` on the commit that closes the last gate.
- `repro/STRANGER_LOG.md` records the date + commit + token counts of the verified stranger-test run.

After the v1.0.0 tag, the agentic provider G + any contamination response are explicit v1.1 scope, not v1.0 patches.
