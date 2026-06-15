# Stranger-test log

Records every successful execution of the reproducibility entrypoint
(`make repro TASK=<id>`) from a clean clone. Closes Chunk 6 exit gate #5.

The bar is: byte-identical `input_tokens_norm` for deterministic providers,
within ±1% otherwise. Latency, `run_id`, and `timestamp` are expected to
drift; tokens are not.

## 2026-06-14 — C-local on commit `edc6ab7`

| Field | Value |
|---|---|
| Repo source | `/Users/hgupta163/dev/Token Efficinecy Benchmark` |
| Stranger clone path | `/tmp/tokenbench-stranger` |
| Repo HEAD | `edc6ab7` (`v1.0 close-out plan + refreshed context handoff`) |
| Task | `needle-click-0000` |
| Provider | `rag-bm25` (v0.1.0) |
| Model | `bedrock.anthropic.claude-sonnet-4-5` |
| `dataset_version` | `1.0.0` |
| `harness_version` | `0.1.0` |
| Python | 3.14, deps from `repro/requirements.lock.txt` |
| `.env` | copied from repo root (gateway-format Anthropic API) |

### Snapshot integrity (re-fetched and re-hashed by the stranger)

| Repo | sha256 |
|---|---|
| click | `92137b889431269ee3352ed168f18d01780cce8f98d9fde41500a95fd18147d4` |
| rich | `3d5a2f96c7dd3c492e96b6e2c807bf298dce067d6a44f82bd15731940cf23ff1` |
| httpx | `96c515bffba67d8c75b65859341a391b03fcf20ed86782499f49f268134e59ad` |

All three match the values pinned in `tokenbench/datasets/repo_pins.py`.

### Cell telemetry (stranger vs published `chunk3.jsonl` at `repeat=0`)

| Field | Stranger | Published | Match |
|---|---:|---:|:---:|
| `input_tokens_norm` | 1127 | 1127 | ✓ byte-identical |
| `output_tokens_norm` | 3 | 3 | ✓ byte-identical |
| `cache_tokens_norm` | 0 | 0 | ✓ |
| `build_tokens_norm` | 256705 | 256705 | ✓ byte-identical |
| `native_input` | 1318 | 1318 | ✓ |
| `native_output` | 8 | 8 | ✓ |
| `latency_ms` | 2553 | 2694 | drift expected |
| `score.correct` | true | true | ✓ |

### Verdict

**PASS.** Exit gate #5 closed for the v1.0 freeze. The local-clone path
exercises everything except a missing-from-repo file that would only
appear in network distribution; the post-GitHub-push verification (the
canonical "stranger" run) is documented as a follow-up below.

### Follow-up: post-push verification

Once the user pushes the repo to GitHub from a second device, repeat the
above procedure on the **canonical stranger** machine:

```bash
git clone https://github.com/<user>/<repo>.git /tmp/tokenbench-stranger-gh
cd /tmp/tokenbench-stranger-gh
cp <path-to-.env> .env
cd repro && make repro TASK=needle-click-0000
```

A new row in this log should be appended with the GitHub URL recorded
under "Repo source." That run validates network distribution; the v1.0
local run already validates the harness contract.
