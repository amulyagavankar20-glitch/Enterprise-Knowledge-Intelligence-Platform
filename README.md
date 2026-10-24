# Enterprise Knowledge Intelligence Platform

Document-grounded company knowledge search with authenticated document management, hybrid retrieval, reranking, source citations, and configurable Ollama/OpenRouter answer generation.

## Repository map

```text
backend/app/          FastAPI application and service modules
backend/tests/        Unit and API tests
scripts/              Evaluation, smoke-data, and retrieval-debug commands
frontend/             Runnable browser app
frontend/designs/     Stitch exports and screenshots retained as references
migrations/           Alembic database migrations
test_data/            Synthetic fixture documents and source corpus
reports/evaluation/   Latest machine-readable and Markdown evaluation outputs
reports/evaluation/archive/  Earlier evaluation and smoke outputs
docs/                 Audit and deployment guidance
stored_documents/     Local uploaded originals (private runtime data)
```

## Local development

Use the Conda environment and the existing local PostgreSQL/pgvector, Redis, and Ollama services. Configure private settings in your local `.env`; never commit it. The app serves the browser interface and API from one origin.

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m alembic upgrade head
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. For tests, run `python -m pytest backend -q`. For the live fixed RAG evaluation, run `python scripts\evaluate_rag.py`; append `--semantic-judge` to request model-assisted estimates. The five-document HTTP smoke harness is `python scripts\setup_test_data.py` and uploads documents to the configured database.

See [deployment instructions](docs/DEPLOYMENT.md), [audit and evaluation notes](docs/AUDIT_REPORT.md), and the [frontend guide](frontend/README.md).
