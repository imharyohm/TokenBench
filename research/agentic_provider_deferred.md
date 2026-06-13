# Agentic Provider (Deliverable G) — Deferred to v1.1

> Captured 2026-06-13 during Chunk 6 scoping. Decision: skip G for v1.0; revisit
> in v1.1. v1.0 ships with the 5 static context methods + a calibrated judge.

## What G is

A 6th provider where the **model itself decides what code to read** through an
agent loop, instead of being handed pre-selected context by the harness. Same
`Provider` interface as the existing 5; different mechanism inside.

```
Static providers (current 5):                    Agentic provider (G):
  question → harness picks chunks → model         question → model:
                                                    "grep for X"  → tool returns
                                                    "read file Y" → tool returns
                                                    "read file Z" → tool returns
                                                    ... 10-30 turns ...
                                                    → final answer
```

Concrete: a 6th file `tokenbench/providers/swe_bench_pro.py` that wraps an
agent harness (canonically SWE-bench Pro, but could equally be Cursor's API,
Claude Code driven externally, or a custom MCP tool-loop).

## Why it matters

Real codebase-AI tools (Cursor, Claude Code, Cline, Aider, ChatGPT code
interpreter) all use agent loops, not static retrieval. Without G, the
benchmark measures every context method **except** the dominant pattern in
production tools.

The interesting question G answers: **does the agent end up to the LEFT of
static methods on the Pareto plot (smarter, fewer tokens) or the RIGHT (more
thorough, more tokens)?** Most people assume agents waste tokens; some recent
results suggest the opposite. Nobody has a clean apples-to-apples answer, and
TokenBench would be positioned to give one.

## Why it's expensive

Each turn re-sends the entire conversation history (LLMs are stateless), so
cumulative input tokens grow roughly **quadratically** with turn count:

| Turn | Cumulative input tokens |
|---:|---:|
| 1 | 2k |
| 5 | 15k |
| 10 | 50k |
| 20 | 150k |
| Total over 20-turn task | ~600k |

vs. ~8k for one static-provider call. **One agent task ≈ 50–100× the tokens
of one static task.**

Spend at different scopes:

| Scope | Tasks | Models | Repeats | Approx cost |
|---|---:|---:|---:|---:|
| Pilot | 24 needle | 1 | 1 | $5–15 |
| Modest (single Pareto datapoint) | 24 needle | 1 | 5 | $50–200 |
| Full parity with other 5 providers | 234 (needle + SWE-QA) | 2 | 5 | $3,000–5,000+ |

The "$50–200" estimate floating around the handoff doc was the *modest* scope,
not parity. Parity would dominate the project's cumulative spend by 100×+.

## Why deferring is reasonable

1. **Bottleneck is elsewhere.** v1.0's biggest unfixed gap is the judge (ECE
   0.20 fails) — that blocks SWE-QA evaluation across 9 of 10 method×model
   pairs. Adding G expands the matrix; fixing the judge unlocks the existing
   matrix. Judge wins on impact-per-dollar.
2. **v1.0 already has a complete finding.** Pareto curve across 5 static
   methods on 2 models with calibrated SWE-QA scoring is a publishable result.
   "Static vs. agent" is an extension, not a prerequisite.
3. **Agent token-counting is fragile.** Multi-turn token accounting (cache
   reads, reasoning tokens, tool-result tokens) needs careful adapter work.
   Better to harden the static path first.
4. **Clean release narrative.** v1.0: "5 static context methods,
   calibrated judge." v1.1: "+ agent loops." Two clean stories beats one mixed
   story.

## Why building it is also reasonable (the case I'm preserving here)

- The chunks/architecture spec lists G as part of P6 (Chunk 6). Strictly
  following the spec puts G in v1.0.
- Single comprehensive v1.0 — no follow-up release needed.
- The trace-aware exploit detector (Chunk 6 D) was designed largely *for*
  agent traces. Without G, D defends an attack surface that doesn't exist in
  the v1.0 dataset.
- The "agents eat codebase tasks" angle is the most timely framing for any
  paper or blog post.

## What v1.1 should include

Park these together post-v1.0:

- **G** itself (this doc).
- A pilot run on 24 needle tasks first (~$5–15) before committing to modest or
  full scope. Use the pilot to validate the harness end-to-end (token
  counting, trace capture, exploit detector consuming the trace) cheaply.
- Specific harness choice — SWE-bench Pro vs MCP code agent vs Claude Code
  externally driven. Decide based on what gives the cleanest token accounting
  and trace.
- Re-evaluate cost ceiling: if v1.0 produces a clear public finding, v1.1
  spend can be justified more easily.

## Implementation sketch (for v1.1)

```python
# tokenbench/providers/swe_bench_pro.py
class SweBenchProProvider(Provider):
    def __init__(self, harness="swe-bench-pro", max_turns=30, ...):
        ...

    def build(self, task):
        # No pre-build — agent assembles context at runtime.
        return None

    def retrieve(self, task, artifact):
        agent = SweBenchProAgent(
            repo_path=artifact_root_for(task.meta["repo_id"]),
            tools=["read_file", "grep", "list_dir"],
            max_turns=self.max_turns,
        )
        result = agent.run(task.question)
        return RetrievedContext(
            text=result.answer,
            input_tokens_norm=result.total_input_tokens_norm,
            output_tokens_norm=result.total_output_tokens_norm,
            trace_uri=result.trace_path,  # for Chunk 6 D
        )
```

Same interface as the other 5 providers — drops into the existing sweep
matrix. Trace_uri pipes into the exploit detector via Chunk 5's
`Judge.trace_uri_for(task)` hook.

## Open design questions (for v1.1)

1. **Harness choice.** SWE-bench Pro is canonical/citable. MCP-based custom
   harness is more flexible. Claude Code externally driven would best
   represent how real users experience this — but token counting is hardest.
2. **Tool surface.** Minimum: `read_file`, `grep`, `list_dir`. Adding
   `run_tests` or `git_log` shifts the comparison toward "agent that can
   iterate" rather than "agent that just reads."
3. **Turn cap.** Hard cap on turns prevents runaway loops but artificially
   constrains the comparison.
4. **Caching.** Anthropic prompt caching dramatically reduces re-sending
   history. Should agent runs use it (more realistic) or not (more comparable
   to static methods that don't cache)?
5. **Failure modes.** What does the metric look like when the agent gives up
   without producing an answer? Static methods always produce one.
