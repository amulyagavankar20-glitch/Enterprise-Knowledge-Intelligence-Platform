import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.documents import router as documents_router
from app.api.routes.query import router as query_router
from app.services.structured_logging import install_observability

app = FastAPI(
    title="Enterprise Knowledge Intelligence Platform",
    version="0.1.0",
    description="Document ingestion and retrieval API.",
)

ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host.strip()]
if "*" not in ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

app.include_router(documents_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
install_observability(app)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the browser app from the API origin so browser requests need no permissive CORS policy.
# Keep this mount after all API routes.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / 'frontend'
if (FRONTEND_DIR / 'index.html').is_file():
    app.mount('/', StaticFiles(directory=FRONTEND_DIR, html=True), name='frontend')
