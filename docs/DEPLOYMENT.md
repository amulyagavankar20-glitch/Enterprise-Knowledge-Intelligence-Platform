# Local and container deployment

This is a production-oriented local deployment baseline, not a complete production environment. It includes a non-root API container, health checks, persistent PostgreSQL/Redis/document/model-cache volumes, Redis-backed shared request limits, allowed-host validation, and same-origin static frontend serving. It does not configure TLS, a reverse proxy, managed backups, alerting, or an object store.

## Local Windows development

Keep secrets in the existing local `.env`; do not commit it. Required API settings include a private `JWT_SECRET_KEY` of at least 32 characters. Use the existing database, Redis, and local Ollama setup. In PowerShell:

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. For the fixed RAG evaluation, run `python scripts\evaluate_rag.py`; to additionally request model-assisted support/citation estimates, run `python scripts\evaluate_rag.py --semantic-judge`. The latter sends each evaluation question, answer and retrieved excerpts to the configured generation provider. Its judgments are estimates, not independent verification.

## Docker Compose

1. Ensure Docker Desktop is running and the local Ollama server exposes its API on the host. `host.docker.internal` is used from the API container.
2. In the existing `.env`, manually configure `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`. Use strong private values; the compose file deliberately refuses to start without them. Set `ALLOWED_HOSTS` to the real hostnames when deploying behind a domain.
3. Build and start the stateful dependencies, migrate, then start the API:

```powershell
docker compose up -d postgres redis
docker compose build api
docker compose run --rm api python -m alembic upgrade head
docker compose up -d api
docker compose ps
```

The compose API port binds to `127.0.0.1:8000`. Put a separately hardened TLS reverse proxy in front before remote access. PostgreSQL, Redis, uploaded originals and Hugging Face model cache use persistent volumes. Back up and restrict the `stored_documents` volume alongside the database; it contains original user uploads. Model weights are downloaded into the cache on first use, so the first query can take longer and needs network access unless the cache was prepopulated.

OpenRouter remains optional. If `GENERATION_PROVIDER=openrouter`, provide `OPENROUTER_API_KEY` privately in `.env`. Do not put credentials in source code or frontend assets. The API does not implement password reset, MFA, account lockout, or organization-wide SSO.

## Operational checks and remaining controls

- `RATE_LIMIT_REDIS_REQUIRED=true` in Compose fails closed if Redis is unavailable. Local development can use the process-local fallback (`false`), which is not shared across workers.
- Configure `ALLOWED_HOSTS`, TLS termination, trusted proxy behavior, firewall rules, database/Redis authentication and network restrictions for the actual deployment topology.
- Set up tested encrypted backups, retention, restore drills, monitoring/alerts and log collection. Current request logs omit bodies, query strings and client IPs; audit records are metadata-only. Feedback is stored separately and includes the submitted question/answer.
- The application trusts the local identity/database and role assignment. Admin promotion must be done by an authorized operator; there is no self-service role change.
- Use an access-controlled durable storage volume. The default local filesystem storage is not object storage and does not by itself provide backup or replication.

## Tests

From repository root in PowerShell:

```powershell
conda activate enterprise-rag
$env:RATE_LIMIT_REDIS_REQUIRED = "false"
python -m compileall -q backend migrations
python -m pytest backend -q --tb=short -p no:cacheprovider --basetemp .pytest-tmp-local
```

For the authenticated five-document smoke harness, configure dedicated `RAG_EVAL_EMAIL` and `RAG_EVAL_PASSWORD` in the current PowerShell process, start FastAPI, then run `python scripts\setup_test_data.py`. This uploads/versions test documents and should only be run when that database mutation is intended. The 31-case evaluator instead needs the seeded evaluation owner and running PostgreSQL, BGE models, and generation provider. It writes results under `reports\evaluation\`.
