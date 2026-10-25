# Enterprise Knowledge Intelligence Platform Audit

## Findings and fixes

- Ollama (`qwen3.5:4b` by default) is the only generation provider. Generation logs status/error class, rejects malformed or empty responses and standalone safety labels, asks for complete multi-part answers, and validates citation labels against returned sources. Label validity does not prove factual entailment.
- Original uploads are stored in PostgreSQL by document version. The Alembic migration adds a `document_files` table, and a separate checksum-verifying utility imports legacy files from `stored_documents/` without deleting them. Run verification before manually retiring local copies.
- Vector and full-text retrieval remain owner-filtered; both select only each document's current version. Admin queries can span owners. RRF removes duplicate chunk IDs and context selection removes identical text.
- API identity comes from short-lived JWT bearer tokens instead of caller-supplied `owner_id`. Registration hashes passwords with Argon2 and always assigns `member`; current role is loaded from the database on every request.
- Authentication, query, upload, and feedback have input validation and rate limits. Redis uses an atomic shared counter and privacy-hashed client addresses; local development falls back to a bounded process-local limiter. Configure `RATE_LIMIT_REDIS_REQUIRED=true` for fail-closed deployments. Behind a reverse proxy, configure trusted proxy handling before relying on client IP limits.
- Changed uploads with the same owner and filename create a new version and archive the old one. Exact duplicate uploads return before extraction/embedding. Ingestion rolls back and removes an uncommitted original file after a database failure.
- Added paginated document listing, detail/content viewing, version listing, PostgreSQL-backed original-file download, and owner/admin-scoped deletion.
- Chunk records now store counts from the BGE tokenizer. Chunk boundaries prefer whitespace and keep long words intact when possible.
- PDF extraction uses the declared `pypdf` dependency. The reranker auto-selects CUDA/CPU. Three invalid top-level Python files were replaced with service compatibility imports.
- Alembic import ordering was repaired. The existing database reports migration `ae8ca1c7f2fb (head)`.
- Added structured JSON request logs with request IDs, duration and status; request/response bodies, query strings and client addresses are omitted. Generic exception and validation handlers avoid returning raw input or exception details. Security response headers, a frontend CSP and configurable `ALLOWED_HOSTS` are enabled.
- Added authenticated feedback submission and metadata-only audit events for auth, query and document actions. Audit history is admin-only and paginated. Feedback records contain the question/answer submitted for review; the UI discloses this before submission.
- Added frontend profile/role lookup, role-gated admin audit view, question-and-answer grouping, clickable citations, evidence cards, feedback form, keyboard skip link, deletion-dialog focus handling and status/error surfaces. Browser automation is not configured, so real browser/assistive-technology verification remains outstanding.
- Added a non-root Docker image and Compose configuration with health checks, persistent volumes, internal service networking and shared Redis rate limiting. Added `.env.example` (no credentials) and local/container setup instructions. TLS, reverse proxy, backups, monitoring and production secrets management remain deployment responsibilities.
- Added opt-in model-assisted answer-support, question-coverage, citation-entailment and abstention estimates to the fixed evaluator. The judge uses the local Ollama model by default, so these are not independent verification. Lexical fact checks remain explicitly approximate.
- The workspace has no `.git` directory, so the Git diff could not be inspected. `.env` was not modified.

## Retrieval evaluation

The fixed 31-case suite covers HR, IT, finance, software procedures, employee directory, multi-part/paraphrased questions, and unsupported queries. Retrieval metrics are document-level because the fixtures have no stable chunk labels. The evaluator now keeps expected-source retrieval, per-fact phrase coverage, complete expected-fact sets, citations, unsupported retrieval emptiness, and answer abstention as separate measures. Phrase checks remain approximate and do not prove semantic correctness.

The latest saved 31-case run records an effective threshold of **0.001** in its JSON and reports overall pass **1.0**, Recall@5 **1.0**, MRR **1.0**, nDCG@5 **1.0**, approximate complete expected-fact accuracy and coverage **1.0**, citation-label validity **1.0** (28 answerable responses), and lexical abstention correctness **1.0** (4/4). The code fallback in `backend/app/services/rag.py` is **0.1** when `RERANKER_SCORE_THRESHOLD` is not set; the `.001` artifact therefore reflects an effective environment override, whose source was not inspected. One unsupported query still retrieved a chunk, so unsupported empty-retrieval rate was **0.75**; its answer correctly abstained.

Treat the existing threshold sweep as a diagnostic, not a fresh benchmark: it filters the at-most-five sources already returned at the effective threshold and cannot refill context from deeper reranked candidates. Its `0.1` row is therefore not definitive full-pipeline Recall@5 for a run configured at `0.1`. The row at `0.002663` likewise should not be used to select a production threshold without a separate retrieval run. No threshold recommendation is made from that sweep alone.

The run completed with zero generation errors and average RAG latency **3.6854 seconds** / P95 **6.5443 seconds**. The optional judge scored all 31 cases with zero errors and estimated question coverage, evidence support, citation entailment, and unsupported abstention at **1.0**. This judge uses the same configured model as generation by default, so those correlated model estimates are not independent evidence. Phrase checks are approximate; none of these scores proves semantic correctness, factual faithfulness, or citation entailment.

Phrase matching normalizes punctuation and spacing but remains approximate; it does not prove semantic correctness or faithfulness. Citation label validity only proves that a label maps to a retrieved source, not that the source entails the claim. The threshold-sweep implementation has been relabeled as a post-filter diagnostic; future threshold selection requires evaluation over the full reranked candidate list at each threshold.

## Remaining risks

- `JWT_SECRET_KEY` must be configured before auth routes can issue or validate tokens. Registration cannot elevate roles; promote an admin out-of-band through an authorized database session.
- There is no refresh-token flow, password reset, account lockout, TLS configuration, or load/concurrency test. Redis enforcement is shared across API workers only when Redis is available and required mode is enabled.
- Legacy files may remain in `stored_documents/` until the migration utility imports and verifies them. The API no longer reads from or writes to that directory.
- `DocumentAccess` sharing is not implemented. Members see their own documents; admins can see/manage all documents.
- The version update path uses a row lock but concurrent uploads were not load-tested. Existing historical rows with logical `database://` paths cannot serve the original bytes; new uploads persist originals.
- Compose build/start, TLS proxying, backups/restore, and production deployment controls have not been verified here.

## Test status

- `python -m compileall -q backend migrations`: passed after the current changes.
- `python -m pytest backend -q --tb=short -p no:cacheprovider --basetemp .pytest-tmp-final-work`: **65 passed**. Workspace-local temporary files and disabling the cache plugin avoid the Windows temp/cache warnings without changing permissions.
- Alembic `current`: `ae8ca1c7f2fb (head)`.
- Five-case HTTP smoke test: not run; it now requires a JWT secret, credentials, and a running FastAPI process.
- Live 31-case evaluation with model judge: completed; **31/31 passed**, zero generation/judge errors. Actual metrics and all case results are saved in `reports/evaluation/enterprise_rag_evaluation_results.json` and `reports/evaluation/enterprise_rag_evaluation_report.md`.

## Local PowerShell setup

Add this line to `.env` manually. Keep the generated value private; the app fails closed without a 32-character minimum secret:

```text
JWT_SECRET_KEY=<random secret of at least 32 characters>
```

Generate one locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Legacy file migration defaults to `stored_documents/`; `DOCUMENT_STORAGE_DIR` or the migration utility's `--root` can point to another legacy root.

Start the services:

```powershell
docker compose up -d postgres redis
```

Start FastAPI in a first PowerShell window:

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

`pytest` unit tests do not need evaluation credentials. The 31-case `scripts\evaluate_rag.py` run connects directly to PostgreSQL and uses `RAG_EVAL_USER_ID` (or its configured default); it does not use `RAG_EVAL_EMAIL` or `RAG_EVAL_PASSWORD`. The HTTP smoke harness `scripts\setup_test_data.py` does require a test account. Set dedicated credentials in the second window; set `RAG_EVAL_AUTO_REGISTER=1` only when creating a new member account:

```powershell
conda activate enterprise-rag
$env:RAG_EVAL_EMAIL = "your-test-email@example.com"
$env:RAG_EVAL_PASSWORD = "a-private-password-at-least-12-chars"
$env:RAG_EVAL_AUTO_REGISTER = "1"
python -m pytest backend -q --tb=short -p no:cacheprovider --basetemp .pytest-tmp-final-work
python -m compileall -q backend migrations
python scripts\setup_test_data.py
python scripts\evaluate_rag.py
```

To add model-assisted answer-support and citation-entailment estimates, run `python scripts\evaluate_rag.py --semantic-judge`. It sends evaluation questions, answers and retrieved excerpts to the local Ollama model; it is not independent verification.

The smoke script uploads the five fixed documents as the authenticated user; it can create newer document versions and should be run only when that is intended. The evaluation script calls Ollama for retrieved answerable cases. Neither workflow needs a database reset/drop.
