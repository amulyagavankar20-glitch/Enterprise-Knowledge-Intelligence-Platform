from types import SimpleNamespace
from uuid import uuid4

from app.api.routes import reports as reports_route
from app.db.dependencies import get_db
from app.main import app
from app.services.auth import get_current_user
from fastapi.testclient import TestClient


def test_report_endpoint_requires_authenticated_identity():
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app, base_url="http://localhost").post(
            "/api/v1/reports/generate", json={"question": "Review policy?"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


def test_report_endpoint_returns_structured_markdown_without_private_errors(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="member")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(reports_route, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(reports_route, "record_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reports_route,
        "generate_grounded_report",
        lambda *args, **kwargs: {
            "title": "Policy report",
            "question": "Review policy?",
            "markdown": "# Policy report\n\n[Source 1]",
            "sources": [{"document_id": "own-doc", "source_number": 1}],
            "verification": {"status": "verified"},
            "export_formats": ["markdown", "browser_print_to_pdf"],
        },
    )
    try:
        response = TestClient(app, base_url="http://localhost").post(
            "/api/v1/reports/generate",
            json={"title": "Policy report", "question": "Review policy?"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["markdown"].startswith("# Policy report")
    assert response.json()["export_formats"] == ["markdown", "browser_print_to_pdf"]


def test_report_endpoint_returns_safe_validation_failure(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role="member")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(reports_route, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(reports_route, "record_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        reports_route,
        "generate_grounded_report",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private document content")),
    )
    try:
        response = TestClient(app, base_url="http://localhost").post(
            "/api/v1/reports/generate", json={"question": "Review policy?"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502
    assert response.json()["detail"] == "The report could not pass evidence validation."
    assert "private document content" not in response.text
