# Enterprise RAG Evaluation

- Cases: 31
- Overall pass rate: 1.0
- Retrieval success / Recall@5: 1.0
- MRR by expected source document: 1.0
- nDCG@5 by expected source document: 1.0
- Expected-fact answer accuracy (approximate): 1.0
- Per-fact answer coverage (approximate): 1.0
- Evidence expected-fact coverage (approximate): 1.0
- Citation label validity: 1.0
- Citation-scored answers: 28
- Citation presence on answerable cases: 1.0
- Abstention correctness: 1.0
- Unsupported abstention cases scored: 4
- Unsupported queries with empty retrieval: 0.75
- Model-judge coverage / errors: 31 / 0
- Model-estimated answer support / citation entailment: 1.0 / 1.0
- Average / p95 latency (seconds): 3.1507 / 5.7513

## Reranker threshold sweep

| Threshold | Answerable Recall@5 | Unsupported empty retrieval | Unsupported false retrieval |
|---:|---:|---:|---:|
| 0.001 | 1.0 | 0.75 | 0.25 |
| 0.001037 | 1.0 | 0.75 | 0.25 |
| 0.002663 | 0.963 | 1.0 | 0.0 |
| 0.01 | 0.8519 | 1.0 | 0.0 |
| 0.012173 | 0.8519 | 1.0 | 0.0 |
| 0.05 | 0.8148 | 1.0 | 0.0 |
| 0.1 | 0.8148 | 1.0 | 0.0 |
| 0.2 | 0.7778 | 1.0 | 0.0 |
| 0.5 | 0.5926 | 1.0 | 0.0 |
| 0.660656 | 0.5926 | 1.0 | 0.0 |
| 0.998476 | 0.037 | 1.0 | 0.0 |
| 1.0 | 0.0 | 1.0 | 0.0 |

Phrase checks are approximate and do not prove semantic correctness or faithfulness. Citation number validity only confirms that a label maps to a returned source; it does not prove the source entails the claim. Retrieval labels are document filenames because deterministic chunk-level labels are not present in the current fixture/index format.
The optional model judge uses the configured generation provider (the same model by default), so its support and entailment estimates are useful signals but are not independent or conclusive evidence.

Machine-readable detail: `reports/evaluation/enterprise_rag_evaluation_results.json`.
