# LLM Engineering Evaluation Status

- Automated checks after the citation-attribution and RAGAS-runner changes: **98 pytest tests passed**; compileall and Ruff passed.
- A focused live Ollama check verified an uncited factual claim against retrieved evidence and produced a valid `[Source 1]` citation.
- Database and Ollama health checks both succeeded. A post-change 34-case rerun was attempted but interrupted after repeated Ollama HTTP 500 responses during answer generation and claim verification; it produced no complete post-change evaluation artifact.
- The latest complete 34-case artifact is a **pre-fix baseline**: overall pass rate 58.82%, Recall@5 1.0, MRR 1.0, nDCG@5 0.9867, expected-fact accuracy (approximate) 51.72%, and citation-label validity 100%. Fourteen answerable cases were withheld, primarily due to missing citations.
- The prior RAGAS run did **not** score either run: both had null scores because RAGAS 0.2.15 failed to import against the installed `langchain-community` 0.4.2. The repaired runner targets RAGAS 0.4.3 and exits nonzero when scoring fails. The installed optional package was not upgraded because pip dependency resolution began proposing broad dependency changes.
- Approximate lexical checks and local-model RAGAS/verifier scores are not proof of semantic correctness, factual faithfulness, or citation entailment.

See [LLM engineering audit](../../docs/LLM_ENGINEERING_AUDIT.md) and [local evaluation commands](../../docs/DEPLOYMENT.md).
