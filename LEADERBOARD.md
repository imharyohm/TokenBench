# TokenBench v1.0.0 leaderboard

Generated from the local run-records store. Every cell is filtered to the **public split** (DECISIONS.md #2). The held-out split is private and never published.

**Two cost columns** are required by Chunk 6 spec §7: TPCA(V=1) for cold-start cost, TPCA(V=10000) for amortized cost. The right answer depends on your query volume.

**No single-number claim.** A method's place on this table is one (accuracy, tokens) point; the curve across V is what tells you which method fits which regime.

`dataset_version: 1.0.0` · `harness_version: 0.1.0` · `JUDGE_RUBRIC_VERSION: 1.1.0`

## Public-split rankings
### needle (public)

| ★ | provider | model | n cells | n tasks | acc | 95% CI | TPCA(V=1) | TPCA(V=10000) | median tok |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
|   | rag-bm25 | claude-sonnet-4-5 | 40 | 8 | 1.000 | [1.000, 1.000] | 257,824 | 1,145 | 257,839 |
|   | rag-bm25 | gpt-4o-mini | 40 | 8 | 1.000 | [1.000, 1.000] | 257,824 | 1,145 | 257,839 |
| ★ | repo-map | claude-sonnet-4-5 | 40 | 8 | 1.000 | [1.000, 1.000] | 16,023 | 8,055 | 16,022 |
| ★ | repo-map | gpt-4o-mini | 40 | 8 | 1.000 | [1.000, 1.000] | 16,023 | 8,055 | 16,022 |
|   | graphify | claude-sonnet-4-5 | 40 | 8 | 1.000 | [1.000, 1.000] | 112,934 | 1,537 | 112,862 |
|   | raw-dump | gpt-4o-mini | 40 | 8 | 1.000 | [1.000, 1.000] | 80,086 | 80,086 | 80,084 |
|   | graphify | gpt-4o-mini | 40 | 8 | 0.950 | [0.850, 1.000] | 118,878 | 1,618 | 112,862 |
|   | llmlingua-rag | claude-sonnet-4-5 | 40 | 8 | 0.875 | [0.625, 1.000] | 294,061 | 713 | 257,306 |
|   | llmlingua-rag | gpt-4o-mini | 40 | 8 | 0.700 | [0.450, 0.900] | 367,576 | 891 | 257,304 |

_★ marks the Pareto frontier (accuracy vs tokens at V=1)._

### swe_qa (public)

| ★ | provider | model | n cells | n tasks | acc | 95% CI | TPCA(V=1) | TPCA(V=10000) | median tok |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| ★ | rag-bm25 | claude-sonnet-4-5 | 125 | 25 | 0.688 | [0.504, 0.856] | 543,179 | 1,962 | 258,130 |
|   | llmlingua-rag | claude-sonnet-4-5 | 125 | 25 | 0.472 | [0.288, 0.656] | 790,724 | 1,832 | 257,670 |
| ★ | repo-map | claude-sonnet-4-5 | 125 | 25 | 0.376 | [0.208, 0.552] | 43,166 | 21,983 | 16,206 |
|   | graphify | claude-sonnet-4-5 | 125 | 25 | 0.352 | [0.184, 0.520] | 2,079,564 | 6,883 | 117,566 |
|   | rag-bm25 | gpt-4o-mini | 125 | 25 | 0.312 | [0.152, 0.488] | 1,197,249 | 3,797 | 257,866 |
|   | llmlingua-rag | gpt-4o-mini | 125 | 25 | 0.128 | [0.024, 0.256] | 2,914,701 | 5,663 | 257,386 |
|   | repo-map | gpt-4o-mini | 125 | 25 | 0.112 | [0.008, 0.240] | 143,300 | 72,186 | 16,040 |
|   | graphify | gpt-4o-mini | 125 | 25 | 0.064 | [0.000, 0.160] | 11,435,380 | 35,636 | 117,437 |

_★ marks the Pareto frontier (accuracy vs tokens at V=1)._


## Held-out diagnostic

_Held-out numbers are NEVER published in releases. This section exists locally for the maintainer's contamination audit per DECISIONS.md #7._

### needle — public vs held-out gap

| provider | model | acc(public) | acc(heldout) | Δacc | flag |
|---|---|---:|---:|---:|:---:|
| graphify | claude-sonnet-4-5 | 1.000 | 0.933 | +0.067 |   |
| graphify | gpt-4o-mini | 0.950 | 0.907 | +0.043 |   |
| llmlingua-rag | claude-sonnet-4-5 | 0.875 | 0.850 | +0.025 |   |
| llmlingua-rag | gpt-4o-mini | 0.700 | 0.647 | +0.053 |   |
| rag-bm25 | claude-sonnet-4-5 | 1.000 | 0.950 | +0.050 |   |
| rag-bm25 | gpt-4o-mini | 1.000 | 0.950 | +0.050 |   |
| raw-dump | gpt-4o-mini | 1.000 | 0.690 | +0.310 |   |
| repo-map | claude-sonnet-4-5 | 1.000 | 0.643 | +0.357 |   |
| repo-map | gpt-4o-mini | 1.000 | 0.583 | +0.417 |   |

_⚠️ marks |Δacc| > 2× bootstrap CI on public — potential contamination per DECISIONS.md #7._


### swe_qa — public vs held-out gap

| provider | model | acc(public) | acc(heldout) | Δacc | flag |
|---|---|---:|---:|---:|:---:|
| graphify | claude-sonnet-4-5 | 0.352 | 0.209 | +0.143 |   |
| graphify | gpt-4o-mini | 0.064 | 0.030 | +0.034 |   |
| llmlingua-rag | claude-sonnet-4-5 | 0.472 | 0.502 | -0.030 |   |
| llmlingua-rag | gpt-4o-mini | 0.128 | 0.098 | +0.030 |   |
| rag-bm25 | claude-sonnet-4-5 | 0.688 | 0.570 | +0.118 |   |
| rag-bm25 | gpt-4o-mini | 0.312 | 0.336 | -0.024 |   |
| repo-map | claude-sonnet-4-5 | 0.376 | 0.166 | +0.210 |   |
| repo-map | gpt-4o-mini | 0.112 | 0.021 | +0.091 |   |

_⚠️ marks |Δacc| > 2× bootstrap CI on public — potential contamination per DECISIONS.md #7._

