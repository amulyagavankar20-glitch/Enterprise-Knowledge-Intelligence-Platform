# Project audit and evaluation status

This report summarizes the implementation and the evaluation artifacts currently committed in the repository. It is an engineering status report, not a security certification or production-readiness claim.

## Implemented capabilities

- **Authentication and authorization:** JWT bearer authentication, password hashing, database-loaded roles, member-only registration, and owner/admin checks on document and retrieval operations.
- **Document management:** PDF, DOCX, TXT, and Markdown ingestion; versioning; exact duplicate detection; content viewing; PostgreSQL-backed originals; download and deletion workflows.
- **Retrieval:** BGE-large embeddings, PostgreSQL/pgvector search, PostgreSQL full-text search, reciprocal rank fusion, BGE cross-encoder reranking, deduplication, and bounded context selection.
- **Generation:** Local Ollama is the only supported LLM provider. Generation includes source labels, abstention instructions, safe error handling, and optional claim-support estimation.
- **Frontend:** authenticated Q&A, document library, source excerpts, reports, feedback, and admin audit view. Frontend tests exist, but browser/assistive-technology verification is still needed.
- **Operations:** Alembic migrations, Docker Compose, Redis-backed rate limiting, structured request logging, metadata audit events, and safe API error surfaces.

## Latest complete saved evaluation

Artifact: [`enterprise_rag_evaluation_results.json`](../reports/evaluation/enterprise_rag_evaluation_results.json) with its [Markdown report](../reports/evaluation/enterprise_rag_evaluation_report.md).

The artifact is dataset `enterprise-rag-v1`, version 1, with 34 cases and execution status `completed`. It records Ollama `qwen3.5:4b`, `BAAI/bge-large-en-v1.5`, `BAAI/bge-reranker-base`, top 5, and `RERANKER_SCORE_THRESHOLD=0.001` (the artifact says the threshold came from the environment). The result does not record a run timestamp.

| Metric | Saved result | Qualification |
|---|---:|---|
| Overall pass rate | 20/34 (58.82%) | Fixed evaluator criteria |
| Retrieval Recall@5 | 1.0 | Expected source **document**, not chunk |
| MRR | 1.0 | Expected source document ranking |
| nDCG@5 | 0.9867 | Expected source document ranking |
| Approximate expected-fact accuracy | 51.72% | Phrase-based check |
| Approximate expected-fact coverage | 40.00% | Phrase-based check |
| Evidence expected-fact coverage | 100% | Approximate phrase check against retrieved evidence |
| Citation-label validity | 100% (31 scored answers) | Label maps to a returned source; no entailment guarantee |
| Abstention correctness | 100% (5 unsupported cases) | Fixed evaluator judgment |
| Unsupported queries with empty retrieval | 60% | Retrieval diagnostic, not answer correctness |
| Mean / P95 latency | 6.2682 / 16.4517 seconds | Machine/model state affects timing |

The same artifact reports **96.43% approximate expected-fact accuracy for the verification-disabled baseline**, against **51.72% for the verified pipeline**. This is a significant quality regression and must be addressed before presenting verification as an answer-quality improvement. Phrase checks can misclassify paraphrases, but the size of the gap warrants case-level review. The artifact reports no semantic-judge scores.

An earlier timestamped evaluation [`enterprise_rag_evaluation_20261025T114421Z.md`](../reports/evaluation/enterprise_rag_evaluation_20261025T114421Z.md) is **partial**: 30 of 34 cases completed and 4 failed. Its 96.67% pass rate is calculated over the completed subset only. Do not present it as a complete-suite result or compare it directly with the full 34-case rate.

## Remaining engineering risks

- **Answer quality:** inspect the 34 saved case records, especially baseline-versus-verified differences. Improve verifier precision and answer completeness, then evaluate on the fixed set and a manually reviewed semantic sample.
- **Retrieval evaluation:** add stable chunk-level relevance labels and broader, independently held-out documents. The current document-level metrics can overstate whether the exact supporting passage was retrieved.
- **Latency:** the saved metrics are not a controlled before/after benchmark. Record cold and warm timings by retrieval, embedding, reranking, generation, and verification stage on a documented machine before claiming an optimization.
- **Notebook methodology:** the optional BGE fine-tuning notebook now groups connected positive/negative source-document IDs and bases candidate selection on validation. Its test metrics are report-only; its limited triplet-candidate evaluation still does not establish production improvement.
- **Security/deployment:** configure TLS/reverse proxy, trusted proxy behavior, secrets management, encrypted backups and restore drills, monitoring, alerting, and production network controls. MFA, SSO, password reset, and account lockout are not implemented.
- **Frontend quality:** perform browser-level responsive, keyboard, and screen-reader checks; there is no configured browser automation suite.
- **Concurrency and resilience:** database version updates, rate limits, and Ollama behavior need deployment-level concurrency/load testing. Do not run resource-heavy evaluation on a memory-saturated development laptop.

## Recent automated checks

On 2026-10-27, the focused mocked suite for generation, verification, reranking, retrieval, evaluation, and Ollama client behavior reported **52 passed**. `compileall` and `git diff --check` also passed. These checks did not exercise a live PostgreSQL database, BGE model, or Ollama server, and they do not validate the README/documentation edits. Run the commands in [README: Tests and evaluation](../README.md#tests-and-evaluation) when the relevant local services and resources are available.

## Operational boundaries

- PostgreSQL stores originals and derived chunks/vectors. Legacy files may still exist locally until imported and verified; the migration utility does not delete them.
- Redis-backed rate limits are shared only when Redis is configured and required. Process-local fallback is development-only.
- Audit events are metadata-oriented. Feedback intentionally stores the question and answer submitted for review.
- Ollama verification is a model estimate, not proof of entailment. Citation label validity is not factual citation validation.
- GraphRAG and model fine-tuning are not runtime requirements. Add them only when representative evaluations demonstrate a measurable need.
