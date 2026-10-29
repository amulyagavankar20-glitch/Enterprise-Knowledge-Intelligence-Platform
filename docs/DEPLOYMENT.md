# Local and container deployment

This is a production-oriented local deployment baseline, not a complete production environment. It includes a non-root API container, health checks, persistent PostgreSQL/Redis/model-cache volumes, Redis-backed shared request limits, allowed-host validation, and same-origin static frontend serving. Original uploaded bytes, chunks, and embeddings are stored in PostgreSQL. It does not configure TLS, a reverse proxy, managed backups, or alerting.

## Local Windows development

Keep secrets in the existing local `.env`; do not commit it. Required API settings include a private `JWT_SECRET_KEY` of at least 32 characters. Use the existing database, Redis, and local Ollama setup. In PowerShell:

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m alembic upgrade head
python scripts\migrate_document_files.py
python scripts\migrate_document_files.py --verify-only
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The import utility copies originals from `stored_documents/` (or `DOCUMENT_STORAGE_DIR` if set in the current process) to PostgreSQL and checks each file against its recorded SHA-256 checksum. It never deletes local files. Review its JSON results and require zero missing files, checksum mismatches, and failures from `--verify-only` before manually removing old local copies. New uploads are written only to PostgreSQL.

Open `http://127.0.0.1:8000/`. For the fixed RAG evaluation, run `python scripts\evaluate_rag.py`; to additionally request model-assisted support/citation estimates, run `python scripts\evaluate_rag.py --semantic-judge`. The latter sends each evaluation question, answer and retrieved excerpts to the configured Ollama model. Its judgments are estimates, not independent verification.

The evaluation is fixed at dataset `enterprise-rag-v1` (34 cases). It includes a multi-document query and an adversarially worded user query alongside answerable and unsupported cases. Retrieval labels include expected document filenames plus pinned fixture chunk indexes; expected-fact checks are approximate phrase checks. Re-run the evaluator to refresh the result JSON with retrieved contexts. Historical JSON files predate the current schema and are not directly comparable to a newly generated run.

RAGAS is optional and remains local. Keep its compatibility pins out of the API environment: create an isolated evaluation venv that can reuse the already-installed BGE/Ollama client packages, then install the pinned RAGAS stack. Ensure Ollama is reachable and the configured judge model is present before scoring:

```powershell
conda activate enterprise-rag
$ragasEnv = Join-Path $env:TEMP 'enterprise-rag-ragas'
if (-not (Test-Path (Join-Path $ragasEnv 'Scripts\python.exe'))) {
    python -m venv --system-site-packages $ragasEnv
}
& (Join-Path $ragasEnv 'Scripts\python.exe') -m pip install -r requirements-evaluation.txt
& (Join-Path $ragasEnv 'Scripts\python.exe') scripts\evaluate_ragas.py `
  --improved reports\evaluation\enterprise_rag_evaluation_20261029T072902Z.json `
  --baseline reports\evaluation\enterprise_rag_baseline_20261029T072902Z.json `
  --output reports\evaluation\ragas_comparison_20261029.json
```

Replace the timestamped filenames with the pair produced by your run.

The main evaluator writes a same-run verification-disabled baseline alongside the improved verified run. This isolates the effect of verification while using the same retrieval results and contexts. RAGAS uses local Ollama plus the existing BGE embedding model, explicitly disables RAGAS analytics and LangChain remote tracing, and writes per-run failure categories. Its scores are judge estimates; the reference answers are synthesized from expected-fact phrases, so context precision/recall are approximate. The script does not send evaluation prompts to an external provider.

The Reports page calls `POST /api/v1/reports/generate`, uses the authenticated verified-answer pipeline, and offers Markdown download and browser print/Save as PDF. Reports are not persisted. Page numbers are included when PDF text extraction supplies page markers; DOCX references use chunk indices because DOCX page layout is not stable.

DOCX table contents are extracted in body order as labeled rows/cells. PDF selectable text retains page markers. For scanned PDF OCR, install the optional Python packages with `python -m pip install -r requirements-ocr.txt`, install local Poppler and Tesseract executables, and set `DOCUMENT_OCR_ENABLED=true` in your local environment or Compose configuration. `DOCUMENT_OCR_MAX_PAGES` defaults to 20. OCR runs only on pages with no selectable text; OCR failures are returned as safe ingestion errors. Charts and images are not interpreted. Do not enable OCR in a deployment image until its native binaries are installed and verified.

## Docker Compose

1. Ensure Docker Desktop is running and the local Ollama server exposes its API on the host. `host.docker.internal` is used from the API container.
2. In the existing `.env`, manually configure `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`. Use strong private values; the compose file deliberately refuses to start without them. Set `ALLOWED_HOSTS` to the real hostnames when deploying behind a domain.
3. Build and start the stateful dependencies, migrate the schema and any legacy local originals, then start the API:

```powershell
docker compose up -d postgres redis
docker compose build api
docker compose run --rm api python -m alembic upgrade head
docker compose run --rm api python scripts/migrate_document_files.py
docker compose run --rm api python scripts/migrate_document_files.py --verify-only
docker compose up -d api
docker compose ps
```

The compose API port binds to `127.0.0.1:8000`. Put a separately hardened TLS reverse proxy in front before remote access. PostgreSQL, Redis and the Hugging Face model cache use persistent volumes. PostgreSQL contains original user uploads and must be backed up and access-restricted. Model weights are downloaded into the cache on first use, so the first query can take longer and needs network access unless the cache was prepopulated.

Ollama is the only supported generation provider. Start the Ollama service, pull the configured model with `ollama pull qwen3.5:4b`, and set `OLLAMA_MODEL` and `OLLAMA_API_URL` for the runtime topology. In Compose, the default URL uses `host.docker.internal`. Troubleshoot connectivity from the API container and confirm the model is listed with `ollama list`. The API does not implement password reset, MFA, account lockout, or organization-wide SSO.

## Operational checks and remaining controls

- `RATE_LIMIT_REDIS_REQUIRED=true` in Compose fails closed if Redis is unavailable. Local development can use the process-local fallback (`false`), which is not shared across workers.
- Configure `ALLOWED_HOSTS`, TLS termination, trusted proxy behavior, firewall rules, database/Redis authentication and network restrictions for the actual deployment topology.
- Set up tested encrypted backups, retention, restore drills, monitoring/alerts and log collection. Current request logs omit bodies, query strings and client IPs; audit records are metadata-only. Feedback is stored separately and includes the submitted question/answer.
- The application trusts the local identity/database and role assignment. Admin promotion must be done by an authorized operator; there is no self-service role change.
- Include PostgreSQL original-file blobs in encrypted backups and test restore procedures; database storage does not by itself provide backup or replication.

## Tests

From repository root in PowerShell:

```powershell
conda activate enterprise-rag
$env:RATE_LIMIT_REDIS_REQUIRED = "false"
python -m compileall -q backend migrations
python -m pytest backend -q --tb=short -p no:cacheprovider --basetemp .pytest-tmp-local
python scripts\evaluate_rag.py
```

For the authenticated five-document smoke harness, configure dedicated `RAG_EVAL_EMAIL` and `RAG_EVAL_PASSWORD` in the current PowerShell process, start FastAPI, then run `python scripts\setup_test_data.py`. This uploads/versions test documents and should only be run when that database mutation is intended. The 34-case evaluator instead needs the seeded evaluation owner, running PostgreSQL, BGE models, and Ollama. It writes improved and same-run verification-disabled baseline results under `reports\evaluation\`.
