# RAG pipeline configuration

The application uses the pretrained `BAAI/bge-large-en-v1.5` encoder and `BAAI/bge-reranker-base` cross-encoder, followed by local Ollama generation and claim-support estimation. Fine-tuning is not part of the runtime pipeline. The optional Colab notebook under `notebooks/` groups positive/negative source documents and uses validation for candidate selection; its candidate-pool metrics are not production retrieval metrics.

## Current retrieval settings

- Retrieve up to 20 hybrid candidates, rerank them, apply the provisional score threshold, deduplicate, and pass up to 5 chunks to the answer service.
- `RERANKER_SCORE_THRESHOLD=0.001` matches the latest recorded evaluation configuration. It is provisional, not a calibrated probability. Re-evaluate answerable and unsupported questions before changing it or disabling the filter.
- The evaluator's `Recall@5` and ranking metrics are based on expected document filenames, not labeled relevant chunks.

## Runtime and memory settings

The example settings use `EMBEDDING_BATCH_SIZE=16`, `RERANKER_BATCH_SIZE=8`, `OLLAMA_NUM_CTX=4096`, `OLLAMA_NUM_PREDICT=700`, and `OLLAMA_KEEP_ALIVE=5m`. They are conservative defaults for the current pretrained models; device selection remains `auto`. All settings can be overridden through environment variables and are passed to the Docker API container by Compose. Restart the API after changing them.

Changing the embedding model requires confirming its output dimension, migrating the PostgreSQL vector column if that dimension differs, and re-embedding every stored chunk. Never mix vectors from different encoders in the same index.

## Evaluation status

The latest complete saved artifact is `reports/evaluation/enterprise_rag_evaluation_results.json`: 34 cases, threshold 0.001 from the environment, 100% expected-document Recall@5, MRR 1.0, nDCG@5 0.9867, 58.82% overall pass, 51.72% approximate expected-fact accuracy, 100% citation-label validity, and 100% abstention correctness. Mean/P95 latency in that artifact is 6.2682/16.4517 seconds. The artifact has no run timestamp.

Its verification-disabled baseline has 96.43% approximate expected-fact accuracy, versus 51.72% for the verified pipeline. This is a significant quality regression that needs case-level diagnosis; do not claim verification improved correctness. The 100% evidence expected-fact coverage is a phrase match, not semantic evidence validation.

An earlier timestamped artifact completed only 30 of 34 cases; four failed during verification. Its 96.67% pass rate applies to completed cases only and must not be presented as a full-suite result. Phrase-based checks are approximate, citation-label validity does not prove entailment, and the local verifier is a model estimate. See `reports/evaluation/` for the underlying case results and artifact metadata.
