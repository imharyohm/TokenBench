# TokenBench v1.0.0 leaderboard

Generated from the local run-records store. Every cell is filtered to the **public split** (DECISIONS.md #2). The held-out split is private and never published.

**Two cost columns** are required by Chunk 6 spec §7: TPCA(V=1) for cold-start cost, TPCA(V=10000) for amortized cost. The right answer depends on your query volume.

**No single-number claim.** A method's place on this table is one (accuracy, tokens) point; the curve across V is what tells you which method fits which regime.

`dataset_version: 1.0.0` · `harness_version: 0.1.0` · `JUDGE_RUBRIC_VERSION: 1.1.0`

## Public-split rankings
### needle (public)

| ★ | provider | model | n cells | n tasks | acc | 95% CI | TPCA(V=1) | TPCA(V=10000) | median tok |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
|   | rag-bm25 | claude-sonnet-4-5 | 24 | 8 | 1.000 | [1.000, 1.000] | 257,824 | 1,145 | 257,839 |
|   | rag-bm25 | gpt-4o-mini | 24 | 8 | 1.000 | [1.000, 1.000] | 257,824 | 1,145 | 257,839 |
| ★ | repo-map | claude-sonnet-4-5 | 24 | 8 | 1.000 | [1.000, 1.000] | 16,023 | 8,055 | 16,022 |
| ★ | repo-map | gpt-4o-mini | 24 | 8 | 1.000 | [1.000, 1.000] | 16,023 | 8,055 | 16,022 |
|   | graphify | claude-sonnet-4-5 | 24 | 8 | 1.000 | [1.000, 1.000] | 112,934 | 1,537 | 112,862 |
|   | raw-dump | gpt-4o-mini | 24 | 8 | 1.000 | [1.000, 1.000] | 80,086 | 80,086 | 80,084 |
|   | graphify | gpt-4o-mini | 24 | 8 | 0.958 | [0.875, 1.000] | 117,844 | 1,604 | 112,862 |
|   | llmlingua-rag | claude-sonnet-4-5 | 24 | 8 | 0.875 | [0.625, 1.000] | 294,061 | 713 | 257,306 |
|   | llmlingua-rag | gpt-4o-mini | 24 | 8 | 0.625 | [0.375, 0.875] | 411,685 | 998 | 257,304 |

_★ marks the Pareto frontier (accuracy vs tokens at V=1)._

### swe_qa (public)

| ★ | provider | model | n cells | n tasks | acc | 95% CI | TPCA(V=1) | TPCA(V=10000) | median tok |
|---|---|---|---:|---:|---:|---|---:|---:|---:|
| ★ | rag-bm25 | claude-sonnet-4-5 | 75 | 25 | 0.693 | [0.520, 0.867] | 538,997 | 1,944 | 258,130 |
|   | llmlingua-rag | claude-sonnet-4-5 | 75 | 25 | 0.480 | [0.293, 0.667] | 777,546 | 1,802 | 257,670 |
| ★ | repo-map | claude-sonnet-4-5 | 75 | 25 | 0.387 | [0.227, 0.560] | 41,974 | 21,375 | 16,214 |
|   | graphify | claude-sonnet-4-5 | 75 | 25 | 0.347 | [0.187, 0.507] | 2,111,562 | 6,994 | 117,566 |
|   | rag-bm25 | gpt-4o-mini | 75 | 25 | 0.293 | [0.133, 0.467] | 1,273,435 | 4,036 | 257,855 |
|   | llmlingua-rag | gpt-4o-mini | 75 | 25 | 0.133 | [0.027, 0.267] | 2,798,111 | 5,434 | 257,392 |
|   | repo-map | gpt-4o-mini | 75 | 25 | 0.107 | [0.013, 0.227] | 150,438 | 75,768 | 16,038 |
|   | graphify | gpt-4o-mini | 75 | 25 | 0.080 | [0.000, 0.187] | 9,148,308 | 28,512 | 117,440 |

_★ marks the Pareto frontier (accuracy vs tokens at V=1)._

