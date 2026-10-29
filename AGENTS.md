# AGENTS.md

Local-first enterprise RAG app: FastAPI API (also serves the frontend), PostgreSQL + pgvector, Redis rate limiting, and local Ollama. Python 3.11, Conda env `enterprise-rag`. Read `docs/RULES.md` before changing security, retrieval, or evaluation behavior; it is binding project policy.

## Commands (PowerShell, from repo root)

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
$env:RATE_LIMIT_REDIS_REQUIRED = "false"   # local fallback; Compose sets true
python -m pytest backend -q --tb=short -p no:cacheprovider --basetemp .pytest-tmp-local
python -m pytest backend/tests/test_retrieval.py::test_hybrid_search_rejects_blank_query -q
python -m compileall -q backend migrations scripts
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

- The backend suite is fully mocked/offline: no PostgreSQL, Redis, or Ollama required. It imports PyTorch/sentence-transformers and takes roughly 30 seconds.
- There is no configured lint, format, or typecheck task (`pyproject.toml` only configures pytest). The GitHub workflows are stale generic templates: Node CI with no `package.json`, and Pylint on Python 3.8-3.10 while the project requires 3.11. Do not follow them or add npm commands.
- Frontend is plain `frontend/index.html`, `app.css`, `app.js`; no build step, bundler, or Node dependencies.
- Live evaluation is not a normal test: `python scripts\evaluate_rag.py` calls local Ollama/PostgreSQL, needs the seeded evaluation owner (`RAG_EVAL_USER_ID`, default embedded UUID), and writes new artifacts under `reports/evaluation/`.
- `python scripts\setup_test_data.py` uploads/versions documents; it needs a running API plus `RAG_EVAL_EMAIL`/`RAG_EVAL_PASSWORD` and mutates the database. Run only when intended.
- `python scripts\migrate_document_files.py` is only for legacy originals in `stored_documents/`. New uploads go to PostgreSQL; the utility never deletes local files.

## Architecture

- Entrypoint: `backend/app/main.py`. Routes are in `backend/app/api/routes/` under `/api/v1`; `/health` is separate; the frontend is mounted last at `/`.
- RAG flow lives in `backend/app/services/rag.py`: owner-filtered pgvector + PostgreSQL full-text search -> reciprocal rank fusion -> BGE reranking -> threshold/dedup -> Ollama generation -> citation/claim verification. Preserve owner filters on every retrieval path.
- Identity and role come from the JWT loaded from the database. Never authorize from a caller-supplied `owner_id`.
- `backend/app/db/models.py` is the SQLAlchemy model source; Alembic migrations are the schema source of truth. Do not make manual schema changes.
- Configuration is read with `os.getenv` at import time, and `.env` is loaded at import in `backend/app/db/database.py`. Restart processes after env changes. Add new settings to `.env.example` and the `api` environment in `docker-compose.yml`.
- Host PostgreSQL is `127.0.0.1:5433` (container port 5432), Redis `6379`, API `127.0.0.1:8000`. Compose deliberately fails without `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`.
- Changing the embedding model or dimension requires migrating the vector column and re-embedding all chunks. Never mix vectors from different encoders.
- The Dockerfile copies only `backend/app`, `migrations`, `scripts/migrate_document_files.py`, `alembic.ini`, and the three frontend assets. Update it if runtime code moves or new assets are added.

## Data and evaluation constraints

- `.env` exists locally. Never print, overwrite, or commit it; never commit private documents or real data.
- Do not reset/drop/truncate user data to make tests pass. Mock Ollama and the database in automated tests.
- `reports/evaluation/` contains historical artifacts. Write new timestamped results instead of overwriting them, report completed/failed case counts, and never present a partial run as a full-suite result.
- Phrase-based fact checks and the local model verifier are approximate. Do not describe them as proof of correctness or citation entailment.
