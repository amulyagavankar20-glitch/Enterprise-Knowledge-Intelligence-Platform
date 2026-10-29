# Enterprise RAG Evaluation

- Execution status: completed
- Cases completed / failed: 34 / 0 of 34
- Metrics use completed cases only: 34
- Effective reranker threshold: 0.001
- Threshold source: environment
- Overall pass rate: 0.9118
- Retrieval success / Recall@5: 1.0
- Chunk-label complete recall@5: 0.9655
- Chunk-label per-document recall@5: 0.9667
- Chunk MRR / nDCG@5: 0.9655 / 0.9739
- Chunk-labeled cases: 29
- MRR by expected source document: 1.0
- nDCG@5 by expected source document: 0.9867
- Expected-fact answer accuracy (approximate): 0.931
- Verification-disabled baseline expected-fact accuracy (approximate): 0.931
- Per-fact answer coverage (approximate): 0.96
- Evidence expected-fact coverage (approximate): 1.0
- Citation label validity: 1.0
- Verification-disabled baseline citation-label validity: 1.0
- Citation-scored answers: 31
- Citation presence on answerable cases: 1.0
- Abstention correctness: 0.8
- Verification-disabled baseline abstention correctness: 0.75
- Unsupported abstention cases scored: 5
- Unsupported queries with empty retrieval: 0.6
- Model-judge coverage / errors: 0 / 0
- Model-estimated answer support / citation entailment: None / None
- Average / p95 latency (seconds): 2.9769 / 8.4323
- Average retrieval / answer-generation / verification latency (ms): 491.83 / 1005.15 / 1479.63
- Average evaluator-only baseline generation latency (ms; excluded above): 1319.11

## Verification-disabled baseline vs verified pipeline

| Metric | Baseline | Verified pipeline |
|---|---:|---:|
| Expected-fact accuracy (approximate) | 0.931 | 0.931 |
| Citation-label validity | 1.0 | 1.0 |
| Unsupported-question abstention correctness | 0.75 | 0.8 |

## Reranker threshold sweep

| Threshold | Answerable Recall@5 | Unsupported empty retrieval | Unsupported false retrieval |
|---:|---:|---:|---:|
| 0.001 | 1.0 | 0.6 | 0.4 |
| 0.001037 | 1.0 | 0.6 | 0.4 |
| 0.0022 | 0.931 | 0.8 | 0.2 |
| 0.009425 | 0.8276 | 0.8 | 0.2 |
| 0.01 | 0.8276 | 0.8 | 0.2 |
| 0.05 | 0.7931 | 0.8 | 0.2 |
| 0.1 | 0.7931 | 0.8 | 0.2 |
| 0.2 | 0.7586 | 0.8 | 0.2 |
| 0.395144 | 0.6207 | 1.0 | 0.0 |
| 0.5 | 0.5862 | 1.0 | 0.0 |
| 0.998476 | 0.0345 | 1.0 | 0.0 |
| 1.0 | 0.0 | 1.0 | 0.0 |

Phrase checks are approximate and do not prove semantic correctness or faithfulness. Citation number validity only confirms that a label maps to a returned source; it does not prove the source entails the claim. Retrieval labels include expected document filenames and pinned fixture chunk indexes; chunk labels are alternatives per document and must be regenerated if fixture content or chunking changes.
The optional model judge uses the configured generation provider (the same model by default), so its support and entailment estimates are useful signals but are not independent or conclusive evidence.
Threshold-sweep rows are post-filter diagnostics over the at-most-five sources returned at the effective threshold; they are not independent retrieval runs and can understate alternate-threshold Recall@5 because deeper candidates are unavailable for refill.

Machine-readable detail: `reports/evaluation/enterprise_rag_evaluation_20261029T071931Z.json`.
