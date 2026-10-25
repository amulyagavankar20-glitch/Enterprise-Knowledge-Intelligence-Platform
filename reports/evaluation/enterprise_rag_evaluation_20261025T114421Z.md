# Enterprise RAG Evaluation

- Execution status: partial
- Cases completed / failed: 30 / 4 of 34
- Metrics use completed cases only: 30
- Effective reranker threshold: 0.001
- Threshold source: environment
- Overall pass rate: 0.9667
- Retrieval success / Recall@5: 1.0
- MRR by expected source document: 1.0
- nDCG@5 by expected source document: 1.0
- Expected-fact answer accuracy (approximate): 0.9615
- Verification-disabled baseline expected-fact accuracy (approximate): 1.0
- Per-fact answer coverage (approximate): 0.9286
- Evidence expected-fact coverage (approximate): 1.0
- Citation label validity: 1.0
- Verification-disabled baseline citation-label validity: 1.0
- Citation-scored answers: 27
- Citation presence on answerable cases: 0.9615
- Abstention correctness: 1.0
- Verification-disabled baseline abstention correctness: 1.0
- Unsupported abstention cases scored: 4
- Unsupported queries with empty retrieval: 0.75
- Model-judge coverage / errors: 0 / 0
- Model-estimated answer support / citation entailment: None / None
- Average / p95 latency (seconds): 7.3949 / 15.0757

## Verification-disabled baseline vs verified pipeline

| Metric | Baseline | Verified pipeline |
|---|---:|---:|
| Expected-fact accuracy (approximate) | 1.0 | 0.9615 |
| Citation-label validity | 1.0 | 1.0 |
| Unsupported-question abstention correctness | 1.0 | 1.0 |

## Reranker threshold sweep

| Threshold | Answerable Recall@5 | Unsupported empty retrieval | Unsupported false retrieval |
|---:|---:|---:|---:|
| 0.001 | 1.0 | 0.75 | 0.25 |
| 0.001037 | 1.0 | 0.75 | 0.25 |
| 0.002773 | 0.9231 | 1.0 | 0.0 |
| 0.01 | 0.8077 | 1.0 | 0.0 |
| 0.012173 | 0.8077 | 1.0 | 0.0 |
| 0.05 | 0.7692 | 1.0 | 0.0 |
| 0.1 | 0.7692 | 1.0 | 0.0 |
| 0.2 | 0.7692 | 1.0 | 0.0 |
| 0.5 | 0.5769 | 1.0 | 0.0 |
| 0.660656 | 0.5769 | 1.0 | 0.0 |
| 0.998476 | 0.0385 | 1.0 | 0.0 |
| 1.0 | 0.0 | 1.0 | 0.0 |

Phrase checks are approximate and do not prove semantic correctness or faithfulness. Citation number validity only confirms that a label maps to a returned source; it does not prove the source entails the claim. Retrieval labels are document filenames because deterministic chunk-level labels are not present in the current fixture/index format.
The optional model judge uses the configured generation provider (the same model by default), so its support and entailment estimates are useful signals but are not independent or conclusive evidence.
Threshold-sweep rows are post-filter diagnostics over the at-most-five sources returned at the effective threshold; they are not independent retrieval runs and can understate alternate-threshold Recall@5 because deeper candidates are unavailable for refill.

Machine-readable detail: `reports/evaluation/enterprise_rag_evaluation_20261025T114421Z.json`.
