from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import audit as audit_route
from app.api.routes import feedback as feedback_route
from app.api.routes import query as query_route
from app.db.dependencies import get_db
from app.db.models import AuditLog, QueryFeedback, User
from app.main import app
from app.services import auth


def test_frontend_assets_are_served_with_security_headers():
    client = TestClient(app)
    page = client.get("/")
    script = client.get("/app.js")
    assert page.status_code == 200
    assert 'id="app"' in page.text
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["x-request-id"]
    assert "content-security-policy" in page.headers
    assert script.status_code == 200
    assert "api/v1" in script.text


def test_feedback_is_authenticated_scoped_and_audited_without_answer_text(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    user = User(
        id=uuid4(), email="member@example.com", password_hash="unused", role="member",
        is_active=True,
    )

    class FakeDB:
        def __init__(self):
            self.rows = []

        def get(self, model, user_id):
            return user if model is User and user_id == user.id else None

        def add(self, row):
            if isinstance(row, QueryFeedback):
                row.id = uuid4()
            self.rows.append(row)

        def commit(self):
            pass

        def refresh(self, row):
            pass

        def rollback(self):
            pass

    db = FakeDB()
    monkeypatch.setattr(feedback_route, "enforce_rate_limit", lambda *args, **kwargs: None)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    token = auth.create_access_token(user.id)
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/feedback",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Where does the employee work?",
                "answer": "The employee is in Pune [Source 1].",
                "rating": 1,
                "comment": "Helpful",
            },
        )
        unauthenticated = client.post(
            "/api/v1/feedback",
            json={"question": "q", "answer": "a", "rating": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert unauthenticated.status_code == 401
    feedback = next(row for row in db.rows if isinstance(row, QueryFeedback))
    assert feedback.user_id == user.id
    assert feedback.rating == 1
    audit = next(row for row in db.rows if isinstance(row, AuditLog))
    assert audit.actor_id == user.id
    assert "question" not in audit.details
    assert "answer" not in audit.details


def test_audit_log_endpoint_rejects_members_before_query():
    member = type("Member", (), {"role": "member"})()

    class NoQueryDB:
        def query(self, model):
            raise AssertionError("Member audit request must not query audit rows")

    with pytest.raises(HTTPException) as denied:
        audit_route.list_audit_events(NoQueryDB(), member, limit=10, offset=0)
    assert denied.value.status_code == 403


def test_profile_endpoint_is_registered():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/audit" in paths
    assert "/api/v1/feedback" in paths


def test_query_provider_errors_are_not_exposed_to_api_clients(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(query_route, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(query_route, "record_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        query_route,
        "answer_question",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("private upstream payload and credential details")
        ),
    )
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/query/"})
    with pytest.raises(HTTPException) as failed:
        query_route.query_documents(
            request,
            "question",
            object(),
            User(id=uuid4(), email="member@example.com", password_hash="x", role="member"),
        )
    assert failed.value.status_code == 502
    assert "private upstream" not in failed.value.detail
