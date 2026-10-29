# LLM Engineering Evaluation Status

- **Automated checks:** 122 mocked/offline backend tests passed on 2026-10-29. `compileall` and `git diff --check` passed. No Ruff or mypy task is configured.
- **Live RAG evaluation:** 34/34 cases completed with no failed stages using local PostgreSQL, Redis, and Ollama (`qwen3.5:4b`): [JSON](enterprise_rag_evaluation_20261029T072902Z.json), [Markdown](enterprise_rag_evaluation_20261029T072902Z.md).
- **Retrieval and answer metrics:** overall pass 91.18% (31/34); query retrieval success@5 100% (29/29); expected source-label Recall@5 96.67% (29/30); chunk-complete Recall@5 96.55% (28/29); expected source-label Precision@5 20.00% using fixed K=5; document MRR/nDCG@5 1.000/0.9867; chunk MRR/nDCG@5 0.9655/0.9739; approximate expected-fact accuracy 93.10%; citation-label validity 100%; unsupported-question abstention correctness 80% (4/5).
- **RAGAS:** the repaired local runner scored 29 answerable cases with no metric failures: faithfulness 0.971264, answer relevancy 0.885210, context precision 0.942529, and context recall 0.959770. See [JSON](ragas_comparison_20261029T080223Z.json) and [Markdown](ragas_comparison_20261029T080223Z.md). These are local `qwen3.5:4b` estimates using approximate references; no RAGAS baseline was scored.
- **Latency:** retrieval plus answer generation averaged 1.440 seconds (P95 4.650 seconds), excluding verification. The complete verified RAG response averaged 3.0766 seconds (P95 7.8185 seconds) in the single development-machine run.
- **Prior verifier regression:** the old 51.72% verified expected-fact result versus 96.43% baseline came from uncited lead-in sentences being parsed as claims and all-or-nothing rejection. The current verifier excludes those lead-ins and removes unsupported sentences while retaining supported claims. Current results do not prove factual correctness.
- **Remaining evaluation failures:** case 21 paraphrases “pull request” past the phrase check; case 28 misses an IT chunk in a multi-document query; case 34 infers an unsupported conflict-precedence rule that the local verifier did not catch. The optional semantic judge in `evaluate_rag.py` was not run.
- **Historical compatibility issue:** the older RAGAS 0.2.15 attempt failed to import with the then-installed LangChain Community 0.4.2. A separate RAGAS 0.4.3 environment now works; the main application environment was not upgraded for that scoring run.

Lexical checks, citation-label validity, the local verifier, and RAGAS are not proof of semantic correctness or citation entailment. The 34-case data set is small; treat these measurements as a project baseline.

See the [LLM engineering audit](../../docs/LLM_ENGINEERING_AUDIT.md) and [local evaluation commands](../../docs/DEPLOYMENT.md).
