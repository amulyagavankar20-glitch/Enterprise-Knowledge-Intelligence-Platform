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

Artifact: [`enterprise_rag_evaluation_20261029T072902Z.json`](../reports/evaluation/enterprise_rag_evaluation_20261029T072902Z.json) with its [Markdown report](../reports/evaluation/enterprise_rag_evaluation_20261029T072902Z.md).

The artifact is dataset `enterprise-rag-v1`, version 1, with 34 cases and execution status `completed` (34 completed, 0 failed). It records Ollama `qwen3.5:4b`, `BAAI/bge-large-en-v1.5`, `BAAI/bge-reranker-base`, top 5, and `RERANKER_SCORE_THRESHOLD=0.001` (the artifact says the threshold came from the environment). The run used the live local PostgreSQL, Redis, and Ollama services on 2026-10-29.

| Metric | Latest result | Qualification |
|---|---:|---|
| Overall pass rate | 31/34 (91.18%) | Fixed evaluator criteria |
| Query retrieval success@5 | 1.0 (29/29) | At least one expected source document was retrieved per answerable query |
| Expected source-label Recall@5 | 0.9667 (29/30) | Recall over all expected source-document labels |
| Expected source-label Precision@5 | 0.20 | 29 relevant labels / 145 fixed top-five slots; thresholding returns fewer than five contexts on average |
| Chunk-complete Recall@5 | 0.9655 (28/29) | Every expected document had a pinned expected chunk in context |
| Chunk-label recall@5 | 0.9667 (29/30) | Fraction of expected document/chunk labels retrieved |
| Chunk MRR / nDCG@5 | 0.9655 / 0.9739 | Labeled chunk ranking |
| Document MRR / nDCG@5 | 1.0 / 0.9867 | Best-match document ranking |
| Approximate expected-fact accuracy | 93.10% | Phrase-based check |
| Approximate expected-fact coverage | 96.00% | Phrase-based check |
| Evidence expected-fact coverage | 100% | Approximate phrase check against retrieved evidence |
| Citation-label validity | 100% (31 scored answers) | Label maps to a returned source; no entailment guarantee |
| Abstention correctness | 80% (5 unsupported cases) | Fixed evaluator judgment |
| Unsupported queries with empty retrieval | 60% | Retrieval diagnostic, not answer correctness |
| Mean / P95 latency | 3.0766 / 7.8185 seconds | Single run; machine/model state affects timing |

The separate [RAGAS report](../reports/evaluation/ragas_comparison_20261029T080223Z.md) scores 29 answerable cases with usable contexts and approximate references; all four metrics completed without failures: faithfulness 0.9713, answer relevancy 0.8852, context precision 0.9425, and context recall 0.9598. These are local `qwen3.5:4b` judge estimates, not proof of correctness or citation entailment. No compatible RAGAS baseline was scored. A direct hallucination rate is unavailable; `1 - faithfulness` is only an approximate unsupported-claim proxy.

The earlier pre-fix artifact [`enterprise_rag_evaluation_results.json`](../reports/evaluation/enterprise_rag_evaluation_results.json) reported **96.43% approximate expected-fact accuracy for the verification-disabled baseline**, against **51.72% for the verified pipeline**, with 14 answerable cases withheld. The gap was traced to the verifier treating uncited introductory/meta sentences as unsupported factual claims and then withholding the whole answer under all-or-nothing rejection. The current verifier excludes uncited discourse lead-ins, keeps cited factual sentences, and removes only unsupported sentences when at least one claim is supported. In this run **0 answerable cases were withheld** (31 verified, 3 abstained), four answers had unsupported sentences removed, and verified accuracy was 93.10% versus 92.86% for the baseline (the baseline is scored over 28 of 29 answerable cases because one baseline generation failed). That closes the regression on this dataset; it does not prove the verifier improves factual correctness.

The three remaining failures are: case 21, where the answer paraphrases “pull request” so the phrase check misses it (baseline also fails); case 28, a multi-document question whose IT-security chunk was not retrieved, so the unsupported sentence was correctly removed and the chunk metric records the miss; and case 34, a conflict-precedence question that both baseline and verified pipelines answer with an inferred rule no document states, which the local verifier did not catch. The artifact reports no semantic-judge scores.

An earlier timestamped evaluation [`enterprise_rag_evaluation_20261025T114421Z.md`](../reports/evaluation/enterprise_rag_evaluation_20261025T114421Z.md) is **partial**: 30 of 34 cases completed and 4 failed. Its 96.67% pass rate is calculated over the completed subset only. Do not present it as a complete-suite result or compare it directly with the full 34-case rate.

## Remaining engineering risks

- **Answer quality:** the verifier regression is fixed and the latest run has no withheld answerable cases, but the local verifier remains a weak estimate. It did not catch the unsupported conflict-precedence answer in case 34. Improve conflict/precedence handling and verifier precision, then evaluate on the fixed set and a manually reviewed semantic sample.
- **Retrieval evaluation:** pinned chunk-level labels are now scored alongside document labels. The one chunk miss (case 28) shows document-level recall can overstate passage retrieval. Extend labels to broader, independently held-out documents.
- **Latency:** the latest run is not a controlled before/after benchmark. Record cold and warm timings by retrieval, embedding, reranking, generation, and verification stage on a documented machine before claiming an optimization.
- **Notebook methodology:** the optional BGE fine-tuning notebook now groups connected positive/negative source-document IDs and bases candidate selection on validation. Its test metrics are report-only; its limited triplet-candidate evaluation still does not establish production improvement.
- **Security/deployment:** configure TLS/reverse proxy, trusted proxy behavior, secrets management, encrypted backups and restore drills, monitoring, alerting, and production network controls. MFA, SSO, password reset, and account lockout are not implemented.
- **Frontend quality:** perform browser-level responsive, keyboard, and screen-reader checks; there is no configured browser automation suite.
- **Concurrency and resilience:** database version updates, rate limits, and Ollama behavior need deployment-level concurrency/load testing. Do not run resource-heavy evaluation on a memory-saturated development laptop.

## Recent automated checks

On 2026-10-29, after the repository cleanup updates, the full mocked/offline backend suite reported **122 passed**; `compileall` also passed. The separate live 34-case RAG evaluation completed 34/34 cases with no failed stages, and local RAGAS scored 29 usable cases with no metric failures. Tests mostly mock provider/session behavior; they do not prove migrations, OCR binaries, reports in a browser, or model behavior across a broad dataset. Run the commands in [README: Tests and evaluation](../README.md#tests-and-evaluation) when the relevant local services and resources are available.

## Operational boundaries

- PostgreSQL stores originals and derived chunks/vectors. Legacy files may still exist locally until imported and verified; the migration utility does not delete them.
- Redis-backed rate limits are shared only when Redis is configured and required. Process-local fallback is development-only.
- Audit events are metadata-oriented. Feedback intentionally stores the question and answer submitted for review.
- Ollama verification is a model estimate, not proof of entailment. Citation label validity is not factual citation validation.
- GraphRAG and model fine-tuning are not runtime requirements. Add them only when representative evaluations demonstrate a measurable need.
