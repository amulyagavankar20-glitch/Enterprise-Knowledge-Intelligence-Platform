# Product Requirements Document

**Product:** Enterprise Knowledge Intelligence Platform
**Status:** Working prototype / research project
**Audience:** Enterprise employees, knowledge administrators, project contributors, and evaluators

## 1. Product summary

The platform lets authenticated users upload company documents and ask natural-language questions grounded in documents they are authorized to access. Responses should cite retrieved source excerpts, and the system should abstain when the available evidence does not support an answer. Users can manage document versions and provide feedback. Administrators can review metadata audit events.

The system is local-first: PostgreSQL stores application and document data, Redis supports shared rate limits, BGE models handle retrieval, and Ollama generates responses. The product is intended as an evaluated prototype; current answer verification and evaluation metrics do not yet justify production accuracy claims.

## 2. Problem and goals

### Problem

Enterprise knowledge is spread across policies, procedures, and reference documents. Keyword search alone is often insufficient for differently worded questions, while ungrounded generative answers can invent or misstate policy.

### Goals

1. Search the current document versions a user is authorized to access.
2. Return concise answers supported by retrieved evidence and inspectable citations.
3. Abstain when evidence is missing, conflicting, or insufficient.
4. Let users upload, view, version, download, and delete documents safely.
5. Make behavior measurable with a fixed, reproducible evaluation and transparent limitations.
6. Keep inference and document processing under the local deployment's control.

### Non-goals for the current version

- Public multi-tenant SaaS readiness or a claim of production security certification.
- SSO, MFA, password recovery, account lockout, organization-wide sharing, or fine-grained group permissions.
- Guaranteed semantic correctness from automated phrase checks, citations, or LLM judges.
- GraphRAG, automatic knowledge-graph construction, or model fine-tuning in the runtime path.
- OCR interpretation of diagrams, images, or charts.

## 3. Users and permissions

### Member

- Register and sign in.
- Upload and manage documents they own.
- Ask questions over accessible documents.
- Inspect answer sources and submit feedback.

### Administrator

- Has member capabilities.
- Can review authorized cross-owner document data and the paginated audit view according to server-side role checks.
- Admin role assignment is an operator action; registration must not allow a user to select an administrator role.

Identity comes from the authenticated bearer token and current database role, never from a caller-provided `owner_id` field.

## 4. Functional requirements

### Authentication and authorization

- Hash passwords using the configured password-hashing library.
- Issue and validate JWT bearer tokens using a private signing secret.
- Enforce authentication and owner/admin authorization on document and query endpoints.
- Return safe errors that do not expose credentials, SQL details, stack traces, or private document contents.

### Document lifecycle

- Accept PDF, DOCX, TXT, and Markdown with a 20 MiB upload limit.
- Persist original file bytes and version metadata in PostgreSQL.
- Extract text, chunk it, calculate tokenizer-based counts, and store embeddings for searchable content.
- Detect exact duplicate uploads for the same owner before repeating extraction and embedding.
- Create a new version for a changed upload with the same owner and filename.
- Support authorized listing, detail/content viewing, version listing, original download, and deletion.
- Keep legacy filesystem originals until checksum-verified migration is complete; migration tooling must not delete them.

### Question answering

- Search using owner-filtered vector and PostgreSQL full-text paths, fuse rankings, rerank candidates, deduplicate, and select bounded context.
- Use Ollama as the only generation provider in the current product configuration.
- Return source labels tied to the actual retrieved source numbers and expose matching evidence to the UI.
- Abstain instead of fabricating when evidence cannot support the requested facts.
- Treat verification output as an estimate. A valid citation label alone is not proof the cited text entails the claim.

### Web experience

- Provide sign-in, registration, knowledge-base, ask, and reports workflows.
- Present each answer with the associated question, citations, and supporting evidence that can be inspected.
- Keep loading, empty, insufficient-evidence, success, and error states distinguishable.
- Support keyboard navigation and responsive layouts; browser and assistive-technology verification remains a release requirement.

### Feedback, reporting, and audit

- Accept authenticated helpful/not-helpful feedback with optional comments; disclose that question and answer text are stored for review.
- Generate source-grounded reports from authorized evidence; generated reports are not persisted as documents by the current workflow.
- Record metadata audit events for important user actions; restrict audit browsing to administrators.

## 5. Quality attributes and constraints

- **Privacy:** retrieval and document operations must preserve owner-level access filters. Do not log tokens, full prompts, or private source content.
- **Reliability:** model timeouts, invalid responses, and service outages must fail safely and must not turn a failed verification into a verified answer.
- **Performance:** report latency by stage and measure on documented hardware. Model sizes, batch sizes, and context limits must respect available memory.
- **Maintainability:** migrations are the source of schema evolution; keep testable service boundaries and focused regression tests.
- **Portability:** support local Windows/Conda development and Docker Compose deployment documented in `DEPLOYMENT.md`.
- **Evaluation:** preserve deterministic test cases and distinguish retrieval, expected-fact checks, citation labels, abstention, and latency. Report partial runs as partial.

## 6. Current evaluation baseline and acceptance status

The latest complete saved artifact is `reports/evaluation/enterprise_rag_evaluation_results.json` (34 cases; no run timestamp recorded). It reports document-level Recall@5 1.0, MRR 1.0, nDCG@5 0.9867, overall pass 58.82%, approximate expected-fact accuracy 51.72%, citation-label validity 100%, and abstention correctness 100%. Its verification-disabled baseline has approximate expected-fact accuracy of 96.43%.

These results do **not** meet a product-quality acceptance bar for answer correctness. The verifier's observed regression requires case-level diagnosis and a rerun before claiming improvement. The evaluation's retrieval labels are document-level; phrase-based accuracy and coverage are approximate, and citation-label validity does not measure entailment.

### Release acceptance criteria

- All automated unit/API tests pass in the supported environment; failures and unrun service-dependent tests are reported distinctly.
- Cross-owner access tests demonstrate that members cannot retrieve, view, download, or delete another member's data.
- Full evaluation completes all cases or reports a partial status with per-case failure stages.
- Changes to retrieval or verification improve a predeclared held-out answer-quality metric without unacceptable unsupported-answer regressions.
- Browser workflows are checked at desktop and mobile widths, with keyboard navigation and screen-reader labels reviewed.
- Deployment documentation covers secrets, migrations, backups, Ollama connectivity, and operational limits.

## 7. Risks and open decisions

- The saved verified-answer metric underperforms the verification-disabled baseline.
- Current retrieval labels do not identify relevant chunks.
- Answer quality and latency vary with hardware, model state, prompts, and document extraction quality.
- Cross-document sharing, retention/deletion policy, backup retention, and enterprise identity integration require product decisions before production use.
- Fine-tuning remains optional. The notebook groups connected positive/negative source documents and uses validation for candidate selection; its small candidate-pool metrics still need confirmation on a broader, manually labeled benchmark.
