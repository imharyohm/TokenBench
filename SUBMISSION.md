# Submitting a method to TokenBench

> v1.0.0 submission protocol. Local-only at v1.0; the actual public submission flow will be wired in once the project is pushed to GitHub from a second device. This file is the contract that wiring will implement.

## What you submit

A **Provider plugin** that conforms to `tokenbench.providers.base.Provider`, plus its frozen config. That's it. You do not submit:

- Run records (we generate those by running your provider).
- A model adapter (the harness uses its own).
- A judge (the harness uses its own — `AutoContainsJudge` for needle, `LLMJudge` opus-4-7 N=3 for swe-qa, rubric v1.1.0).

## Provider interface

```python
# tokenbench/providers/base.py
class Provider(ABC):
    name: str           # e.g. "rag-bm25"
    version: str        # semver; bump on any code/config change
    config: dict        # frozen, JSON-serializable

    @abstractmethod
    def build(self, task: Task) -> BuildArtifact:
        """One-shot per (provider, task). Returns the indexable artifact
        plus its build_tokens_norm cost (counted once per task)."""

    @abstractmethod
    def retrieve(self, task: Task, artifact: BuildArtifact) -> RetrievedContext:
        """Per-call. Returns the prompt-ready text + input_tokens_norm.
        DOES NOT call the model — the runner does that."""
```

Three rules, all gated by tests in `tests/test_baselines.py` + `tests/test_exploit_detector.py`:

1. **Never read `task.gold` or `task.needle`.** DECISIONS.md #3 isolation boundary. Violations are HIGH findings in `scripts/audit_runs.py` and gate publication.
2. **Token counts use `o200k_base` via `tokenbench.core.tokenizer.count_tokens`.** Native model tokens are captured separately by the model adapter and reconciled at run time. Submitting a different tokenizer is a `dataset_version` boundary violation.
3. **`config` is frozen at submission.** Tuning in response to leaderboard feedback is forbidden by DECISIONS.md #6. If you want to retune, submit a new `version`.

## What gets scored

The harness runs your provider on **both** the public split and the held-out split:

| Split | Manifest | Distributed? |
|---|---|---|
| public | `artifacts/needle/v1.0.0/public_split.tsv` + `artifacts/swe_qa/v1.0.0/public_split.tsv` | Yes |
| held-out | `artifacts/_heldout/needle/v1.0.0/heldout_split.tsv` + `artifacts/_heldout/swe_qa/v1.0.0/heldout_split.tsv` | **No** — local-only |

Both sweeps run at 3 repeats per cell (matching the v1.0.0 rigor sweep). You see the public numbers; the maintainer sees both. The `(public, held-out)` Δacc gap is reported on the leaderboard for every entry, so contamination is exposed but the held-out content is not.

## Cost & verdict columns

Every row reports:

- `n cells`, `n tasks` — cell count after the public-split filter
- `acc` + 95% CI — task-level bootstrap on per-task mean correctness across repeats
- `TPCA(V=1)` — cold-start tokens per correct answer
- `TPCA(V=10000)` — amortized tokens per correct answer
- `median tok` at V=1 — heavy-tail-aware sanity check

The Pareto frontier marker (`★`) is computed at V=1 (cold start). Submitters interested in a different volume can read the curve from the Chunk 6 amortization plot or the iso-budget tables (`run_iso.py`).

## Audit before publication

Before any submission appears on the leaderboard, the maintainer runs:

```bash
python scripts/audit_runs.py --records results/runs/<your-store>.jsonl
```

Per Chunk 6 deliverable D, this scans for:

- **C1** — provider config self-declares gaming markers (`reads_gold`, `reads_needle`, known tactics).
- **C2** — judge-injection patterns in LLM-judge candidate text (HIGH).
- **C3** — paired priors-floor anomaly: if your provider declares "no retrieval" (priors-only), it cannot beat the zero-context floor by more than tolerance T.
- **C4** — placeholder for v1.1 agent-trace gold-path access.

Any HIGH finding gates publication. The exit code is non-zero, the leaderboard regen is not run, and the maintainer follows up. MEDIUM/LOW findings (e.g. the declared `ExploitBaselineProvider` canary) are reported but don't block.

## Re-running an existing entry

The harness is idempotent (DECISIONS.md #4): re-running with the same `(task_id, provider_name, provider_version, model, repeat, seed, dataset_version, harness_version)` cell key is a no-op. To force a re-run, bump `provider.version` — old records remain queryable but are not displayed on the active leaderboard.

## Held-out rotation

The held-out split rotates on the schedule pinned in DECISIONS.md #7:

- 12-month default cadence
- Early-rotation triggers: public-vs-held-out gap > 2× CI on any submitted method, leaked task, or canary string appearing in a model's training corpus disclosure.

When the held-out rotates, all leaderboard entries are archived under their old `dataset_version` with a `superseded_by` pointer. Entries are never deleted; they just stop being displayed on the active leaderboard until re-scored on the new split.

## What v1.0 does NOT yet support

Documented at the top of `research/agentic_provider_deferred.md`:

- **Agentic provider (G).** A provider where the model itself decides which files to read via a tool loop is deferred to v1.1. v1.0 measures static context methods only. Trace-aware exploit detection is wired (Chunk 6 D, C4 placeholder) so the v1.1 agentic provider drops in cleanly.
- **GitHub-hosted submission flow.** v1.0 is local-only; submit via the local repo. The maintainer pushes to GitHub from a second device after v1.0 hardens.

## Submitting

For v1.0 (local-only):

1. Add your provider as `tokenbench/providers/<your_name>.py` and a row in the appropriate provider factory list (e.g. `run_chunk6_rigor.py:PROVIDER_FACTORIES`).
2. Add tests under `tests/test_<your_name>.py`. The existing baselines provide the template.
3. Run `python run_chunk6_rigor.py --dry-run` to confirm the projected cost.
4. Run the live sweep; the run records land in `results/runs/`.
5. `python scripts/audit_runs.py` to check for HIGH findings.
6. `python scripts/generate_leaderboard.py` to regenerate `LEADERBOARD.md`.
7. Open a PR. (Once the GitHub push lands.)
