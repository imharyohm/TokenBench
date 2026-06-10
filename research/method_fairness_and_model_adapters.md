# Method Fairness Protocol + Model Adapters
### Two foundational decisions for TokenBench, explained from scratch

This file expands on two design decisions that came up while planning Chunk 1. Both are referenced in the architecture doc but explained tersely there. This is the long version.

---

## Part 1 — Method-fairness protocol

### The underlying question

Every context method (RAG, Graphify, repo-map, LLMLingua-2) has **settings** that change its behavior:

| Method | Example settings (knobs) |
|---|---|
| RAG | chunk size, top-K retrieved, embedding model, similarity threshold |
| Graphify | graph depth, community detection algorithm, summary length per node |
| Aider repo-map | symbol ranking algorithm, token budget, file-tree fanout |
| LLMLingua-2 | compression ratio, target token count, layer pruning settings |

These settings change the score — sometimes by 10–30% in either direction. So when Method A beats Method B, the question is: **was A genuinely better, or did A's author tune harder?**

The fairness protocol is how you resolve that ambiguity. You pick **one** rule and apply it to every method.

### Option A — Frozen published configs

> "Use whatever the method's authors published as their default. No tuning. Period."

#### What you actually do
1. Go to each method's official repo / paper.
2. Find their default config (usually a YAML, JSON, or hardcoded constant).
3. Record the config as `(commit_sha, config_file_path)` so you have a receipt.
4. Run the benchmark with those configs untouched.

#### What this measures
"What does a normal user get when they install this method off the shelf?"

#### Trade-offs

**Pros:**
- Cheap. No tuning rig, no dev split, no compute budget.
- Hard to game — you literally cannot tune, so no overfitting risk.
- Reflects real-world user experience.
- Defensible claim: "I used commit X's published config, here's the receipt." A reviewer cannot easily attack this.

**Cons:**
- Punishes methods whose defaults are tuned for a different domain (e.g. defaults assume Python web apps, but benchmark uses Rust embedded code).
- Author tuning effort becomes a confound between methods — Aider's repo-map has years of polish in its defaults; a newer method's defaults might be naive.
- Method authors can change "the default" right before your eval. (Mitigation: pin the commit hash.)

### Option B — Equal-budget tuning on a dev split

> "Each method gets the same tuning resources on a private dev split. Configs frozen before scoring on the test split."

#### What you actually do
1. Carve out a **dev split** of tasks (e.g. 20% of the dataset). This is *separate* from your held-out split.
2. Define an equal budget. Pick one of:
   - N GPU-hours of tuning
   - M tokens of tuning compute
   - K hyperparameter trials
3. Each method uses its budget however it likes (grid search, Bayesian opt, manual fiddling) on the dev split.
4. Configs are **frozen** before the test sweep.
5. Tuning logs archived alongside run records.

#### What this measures
"Given equal effort to specialize each method to this benchmark's domain, what does each method achieve?"

#### Trade-offs

**Pros:**
- Removes the "their author tuned harder" confound between methods.
- Methods get to put their best foot forward on your domain.
- Closer to how someone deploying a method in production would actually use it.

**Cons:**
- Expensive. Need a tuning rig per method, dev split, compute log.
- "Equal budget" is itself a judgment call. Is 50 GPU-hours equal to 1M tokens? Methods that benefit more from one resource get an edge.
- Risk of dev-split overfitting if the budget is too generous.
- Shrinks your test set (20% of tasks now go into the dev split, can't be scored).

### Concrete example to show the difference

You're benchmarking **RAG vs Graphify** on RepoQA.

**Under Frozen:**
- RAG runs with LangChain's default: chunk_size=1024, top-K=5, OpenAI ada embeddings.
- Graphify runs with its repo's default: depth=3, community_size=10.
- Result: RAG 65%, Graphify 71%.

A reader objects: "Of course Graphify won. Nobody runs RAG with K=5 on real codebases — production RAG uses K=20 with code-bert. You measured a strawman."

**Under Equal-Budget (4 hours each):**
- RAG searches over (chunk_size, top-K, embedder) on the dev split. Lands at top-K=18, code-bert.
- Graphify searches over (depth, community_size, summary_length). Lands at depth=4.
- Result: RAG 73%, Graphify 70%.

**Same methods, same data, same model — different leaderboard.** This is why §5 #6 of the architecture doc warns that switching mid-stream invalidates prior comparisons.

### Why this is "expensive to retrofit"

If you start with Frozen and switch to Equal-Budget mid-project:
- Prior numbers used different configs than new numbers — not comparable.
- You need a dev split, but tasks may already be published as test data.
- Methods already scored need re-tuning and re-running — expensive cells repeated.

If you start with Equal-Budget and switch to Frozen:
- All tuning effort wasted.
- "Frozen published" might mean a config the authors changed last week — which version do you use? You needed a snapshot policy.

This is why the decision must be locked in **Chunk 1's `DECISIONS.md`** and not revisited later.

### The recommendation

**Pick Frozen for TokenBench.**

Three reasons:

1. **Solo-team realism.** Equal-Budget needs a tuning system per method (each method has different knobs and consumes different resources). That's weeks of engineering before you score anything.

2. **Asymmetric risk.** Frozen lets you add Equal-Budget numbers later as a secondary table. You cannot easily *remove* tuning bias once it's in the headline.

3. **Defensibility.** "I used commit X's published config" is a stronger claim than "we tuned each one for 4 hours and we *think* the budget was fair."

### What to write in `DECISIONS.md`

```markdown
## Method-fairness protocol: FROZEN PUBLISHED CONFIGS

For each provider, we use the configuration published by the method's
authors as of the dataset_version freeze date. Configurations are recorded
as (commit_sha, config_file_path) and stored in
providers/<name>/frozen_config.yaml. Tuning during scoring is forbidden.

Rationale: keeps tuning effort from confounding method comparison and
reflects how a typical user encounters the method. Costs equal-budget
fairness; mitigated by reporting upstream config provenance.

Switching to equal-budget tuning would require a new dataset_version.
```

### Escalation path

If a method's author publicly claims "you used a stale config of mine," you can run a one-time **Equal-Budget addendum** using a *new* `dataset_version`. The original Frozen leaderboard stays intact. The addendum is a controlled escalation, not a rebuild.

---

## Part 2 — Model adapters

### What a model adapter is

A **model adapter** is a thin wrapper around one AI provider's SDK that makes it look identical to every other provider's adapter.

Your benchmark code never calls Anthropic or OpenAI SDKs directly. It calls a generic `Model` interface. The adapter translates that interface into the provider's specific SDK calls.

### Why you need one — the SDK shape problem

Different providers return the same conceptual response in different shapes:

```python
# Anthropic
response = anthropic.messages.create(model="claude-...", messages=[...])
text = response.content[0].text
input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens

# OpenAI
response = openai.chat.completions.create(model="gpt-...", messages=[...])
text = response.choices[0].message.content
input_tokens = response.usage.prompt_tokens         # different field name
output_tokens = response.usage.completion_tokens    # different field name

# Gemini
# yet another different shape
```

Without an adapter layer, every place in the codebase that touches a model needs `if anthropic ... elif openai ...` branches. Maintenance disaster, hard to test, easy to introduce bugs.

### What the adapter actually does

It hides all SDK differences behind one interface:

```python
class Model(ABC):
    name: str                    # e.g. "claude-sonnet-4-5"
    provider: str                # e.g. "anthropic"

    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> ModelResponse:
        ...

class ModelResponse:
    text: str
    native_input_tokens: int     # from provider's usage API (ground truth)
    native_output_tokens: int    # from provider's usage API (ground truth)
    norm_input_tokens: int       # re-counted in o200k_base (cross-model fair)
    norm_output_tokens: int      # re-counted in o200k_base (cross-model fair)
    latency_ms: int
    raw_trace: dict              # full provider response, archived to trace_uri
```

`models/anthropic.py` implements this against Anthropic SDK.
`models/openai.py` implements this against OpenAI SDK.
The runner, providers, and scorers don't know or care which is in use.

### Why the adapter is critical for THIS benchmark specifically

Three reasons, each tied to a specific requirement in `tokenbench_architecture.md`:

#### 1. Token telemetry is the whole point of the benchmark
§1 component [4] mandates: "Adapters pull **token usage from the provider's usage API** (ground truth) and re-count in the reference tokenizer for fair cross-model comparison."

The adapter is where **both** these recordings happen:
- Native tokens from the SDK's response (so the numbers match the billing dashboard)
- Normalized tokens via `tiktoken.get_encoding("o200k_base")` (so comparisons across providers are fair)

Without an adapter, every provider plugin would do this itself, and they'd do it inconsistently. Centralizing it in the adapter means **one place to test, one place to fix bugs**.

#### 2. Multi-model is non-negotiable later
§3 P3 implies you'll run methods across multiple models. The adapter pattern means adding GPT-5 / Gemini is **one new file**, not a code-wide refactor.

This matters because Chunk 6 (release) requires the leaderboard to span multiple models. If you defer the adapter abstraction, you'll be doing emergency surgery in Chunk 6.

#### 3. The trace audit requirement (Chunk 6's exploit detector)
The doc says traces are non-negotiable: "outcome-only scoring can't tell 'solved' from 'exploited the harness'." Chunk 6 needs a trace-aware exploit detector that flags runs whose tool calls touched gold-answer files outside the provider's returned context.

The adapter is the **chokepoint** where every API call passes through. So it's the natural place to log the full trace. Without an adapter, traces would be scattered across provider-specific code paths and the audit becomes much harder.

### What goes inside the adapter

A complete adapter does these jobs:

1. **Translate** generic `complete(prompt, **kwargs)` into provider-specific SDK calls.
2. **Capture native tokens** from the provider's usage API.
3. **Re-count tokens** in `o200k_base` for the normalized fields.
4. **Time** the request (latency_ms).
5. **Log the full trace** (request payload + response) to `trace_uri`.
6. **Translate errors** into a provider-agnostic exception type so the runner can handle rate limits / timeouts uniformly.
7. **Handle retries** with exponential backoff (one place, not scattered).
8. **Pin a model version** so `claude-sonnet-4-5` always means the same model across the run.

### Why Anthropic specifically as the first adapter

You're building this benchmark with Claude as your dev tool. So:

- **You already have an API key.** No friction to start.
- **You already know the SDK shape.** Less time spent debugging boilerplate.
- **Anthropic's usage API returns clean token counts.** Every response includes `usage.input_tokens` and `usage.output_tokens` — no extra calls needed.
- **Cost control during dev.** Sonnet/Haiku are cheap enough that you can run thousands of dev cells without burning your budget. You'll run a *lot* of cells while debugging Chunks 1–4.
- **No reason to start with two providers.** You'd just be doing twice the work for the same Chunk 2 exit gate.

The architecture stays multi-provider from day one. The `Model` base class is generic. Anthropic is just the **first** concrete implementation. When you add OpenAI in Chunk 3 or beyond, it's `models/openai.py` conforming to the same interface — no other code changes.

### Concrete sketch of what `models/anthropic.py` will look like

```python
import time
import anthropic
import tiktoken
from .base import Model, ModelResponse

ENCODER = tiktoken.get_encoding("o200k_base")

class AnthropicModel(Model):
    def __init__(self, model_name: str, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.name = model_name
        self.provider = "anthropic"

    def complete(self, prompt: str, max_tokens: int = 1024, **kwargs) -> ModelResponse:
        t0 = time.time()
        resp = self.client.messages.create(
            model=self.name,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        latency_ms = int((time.time() - t0) * 1000)

        text = resp.content[0].text

        return ModelResponse(
            text=text,
            native_input_tokens=resp.usage.input_tokens,
            native_output_tokens=resp.usage.output_tokens,
            norm_input_tokens=len(ENCODER.encode(prompt)),
            norm_output_tokens=len(ENCODER.encode(text)),
            latency_ms=latency_ms,
            raw_trace={"request": {"prompt": prompt, "model": self.name},
                       "response": resp.model_dump()},
        )
```

This is roughly 30 lines. Adding `models/openai.py` later is another 30 lines, conforming to the same `Model` interface. Nothing in the runner, the providers, or the scorers changes.

### What goes in `DECISIONS.md`

```markdown
## Model adapter architecture

All model providers conform to `tokenbench.models.base.Model`. Adapters
must:
- Capture native tokens from the provider's usage API
- Re-count input + output in o200k_base via tiktoken
- Record latency in ms
- Log full request/response to trace_uri

Adapters live in `tokenbench/models/<provider>.py`. Adding a provider
requires only a new adapter file conforming to the Model ABC.

First adapter: Anthropic (Chunk 2). Additional providers added as needed
in later chunks (Chunk 3+).
```

---

## Summary

| Decision | Pick | Why |
|---|---|---|
| Method fairness | **Frozen published configs** | Cheaper, defensible, can add equal-budget later as addendum |
| Model adapter strategy | **Generic `Model` ABC, Anthropic as first concrete impl** | Single chokepoint for token telemetry + traces; multi-model via new files only |

Both decisions are locked into Chunk 1's `DECISIONS.md`. They are referenced — but not explained at this depth — in the architecture doc (§5 #6 for fairness, §1 [4] for adapters). This file is the long-form rationale.
