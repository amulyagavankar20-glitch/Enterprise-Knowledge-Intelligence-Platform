# Optional RAGAS Evaluation

Dataset: `enterprise-rag-v1` v1
Source evaluation: `enterprise_rag_evaluation_20261029T072902Z.json` (2026-10-29T07:29:02.671738+00:00)
Judge: `ollama / qwen3.5:4b`; embedding: `BAAI/bge-large-en-v1.5`
Generation model: `qwen3.5:4b`; reranker: `BAAI/bge-reranker-base`
Retrieval top K: `5`; reranker threshold: `0.001` (environment)

| Run | Cases | Metric failures | Faithfulness | Answer relevancy | Context precision | Context recall |
|---|---:|---:|---:|---:|---:|---:|
| improved | 29 | 0 | 0.971264 | 0.88521 | 0.942529 | 0.95977 |

Scores are local model estimates, not proof of correctness or entailment. References are approximate. Only the improved run was scored; no baseline deltas are claimed.
