# RAG pipeline configuration

The application uses the pretrained `BAAI/bge-large-en-v1.5` encoder and `BAAI/bge-reranker-base` cross-encoder, followed by local Ollama generation and claim-support estimation. Fine-tuning is not part of the runtime pipeline. The optional Colab notebook under `notebooks/` groups positive/negative source documents and uses validation for candidate selection; its candidate-pool metrics are not production retrieval metrics.

## Current retrieval settings

- Retrieve up to 20 hybrid candidates, rerank them, apply the provisional score threshold, deduplicate, and pass up to 5 chunks to the answer service.
- `RERANKER_SCORE_THRESHOLD=0.001` matches the latest recorded evaluation configuration. It is provisional, not a calibrated probability. Re-evaluate answerable and unsupported questions before changing it or disabling the filter.
- The evaluator computes document-level metrics plus pinned chunk-level alternatives: complete chunk recall, per-label chunk recall, chunk MRR, and chunk nDCG@5. Document-level recall counts a multi-document case as retrieved when at least one expected document is present, so the chunk-complete metric is the stricter passage-retrieval signal.

## Runtime and memory settings

The example settings use `EMBEDDING_BATCH_SIZE=16`, `RERANKER_BATCH_SIZE=8`, `OLLAMA_NUM_CTX=4096`, `OLLAMA_NUM_PREDICT=700`, and `OLLAMA_KEEP_ALIVE=5m`. They are conservative defaults for the current pretrained models; device selection remains `auto`. All settings can be overridden through environment variables and are passed to the Docker API container by Compose. Restart the API after changing them.

Changing the embedding model requires confirming its output dimension, migrating the PostgreSQL vector column if that dimension differs, and re-embedding every stored chunk. Never mix vectors from different encoders in the same index.

## Evaluation status

The latest complete saved artifact is `reports/evaluation/enterprise_rag_evaluation_20261029T072902Z.json`: 34/34 cases completed, threshold 0.001 from the environment, 100% document-level Recall@5, chunk-complete Recall@5 0.9655 (28/29), chunk-label recall 0.9667 (29/30), chunk MRR/nDCG@5 0.9655/0.9739, document MRR 1.0, document nDCG@5 0.9867, 91.18% overall pass, 93.10% approximate expected-fact accuracy, 100% citation-label validity, and 80% abstention correctness. Mean/P95 latency is 3.0766/7.8185 seconds in that run. The run used live local services on 2026-10-29.

The verification-disabled baseline in the same run scored 92.86% approximate expected-fact accuracy over 28 of 29 answerable cases (one baseline generation failed). The earlier pre-fix artifact reported 96.43% baseline versus 51.72% verified with 14 withheld answerable cases; that gap came from uncited lead-in sentences being verified as claims and all-or-nothing rejection withholding entire answers. The verifier now skips uncited discourse lead-ins, retains cited factual sentences, and removes only unsupported sentences while at least one claim is supported. This run had no withheld answerable cases (31 verified, 3 abstained) and four partial removals. It shows the verifier is no longer an accuracy drag on this dataset, not that it improves correctness.

Case 21 fails the phrase check by paraphrasing “pull request”; case 28 is a multi-document query with a missing IT-security chunk; and case 34 infers a conflict-precedence rule that no document states, which the local verifier did not catch. Phrase-based checks are approximate, and the 100% evidence expected-fact coverage is a phrase match, not semantic evidence validation.

An earlier timestamped artifact completed only 30 of 34 cases; four failed during verification. Its 96.67% pass rate applies to completed cases only and must not be presented as a full-suite result. Phrase-based checks are approximate, citation-label validity does not prove entailment, and the local verifier is a model estimate. See `reports/evaluation/` for the underlying case results and artifact metadata.
