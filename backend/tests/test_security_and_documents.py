from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.routes import (
    audit as audit_route,
)
from app.api.routes import (
    auth as auth_route,
)
from app.api.routes import (
    documents,
)
from app.api.routes import (
    feedback as feedback_route,
)
from app.api.routes import (
    query as query_route,
)
from app.db.dependencies import get_db
from app.db.models import DocumentFile, User
from app.services import auth, document_storage, rate_limit
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from starlette.requests import Request


def test_password_hashing_and_verification():
    hashed = auth.hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert auth.verify_password("correct horse battery staple", hashed)
    assert not auth.verify_password("incorrect password", hashed)


def test_access_token_resolves_active_user_from_database(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    user = SimpleNamespace(id=uuid4(), is_active=True, role="member")

    class FakeDB:
        def get(self, model, user_id):
            assert model.__name__ == "User"
            assert user_id == user.id
            return user

    token = auth.create_access_token(user.id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert auth.get_current_user(credentials, FakeDB()) is user


def test_access_token_rejects_missing_and_invalid_credentials(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    with pytest.raises(HTTPException) as missing:
        auth.get_current_user(None, SimpleNamespace())
    assert missing.value.status_code == 401

    bad = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")
    with pytest.raises(HTTPException) as invalid:
        auth.get_current_user(bad, SimpleNamespace())
    assert invalid.value.status_code == 401


def test_register_and_login_routes_hash_passwords_and_issue_tokens(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    user_rows = []

    class Query:
        def __init__(self, model):
            self.model = model
            self.email = None

        def filter(self, clause):
            self.email = clause.right.value
            return self

        def first(self):
            return next((item for item in user_rows if item.email == self.email), None)

    class FakeDB:
        def query(self, model):
            return Query(model)

        def add(self, user):
            if isinstance(user, User):
                user.id = uuid4()
                user_rows.append(user)

        def commit(self):
            pass

        def refresh(self, user):
            pass

        def get(self, model, user_id):
            return next((item for item in user_rows if item.id == user_id), None)

    db = FakeDB()
    app = __import__("app.main", fromlist=["app"]).app

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    email = f"member-{uuid4()}@example.com"
    password = "at-least-twelve-chars"
    try:
        client = TestClient(app, base_url="http://localhost")
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        logged_in = client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        profile = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {logged_in.json()['access_token']}"},
        )
        wrong_password = client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": "wrong-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert registered.status_code == 201
    assert registered.json()["role"] == "member"
    assert user_rows[0].password_hash != password
    assert logged_in.status_code == 200
    assert logged_in.json()["token_type"] == "bearer"
    assert profile.status_code == 200
    assert profile.json()["email"] == email
    assert profile.json()["role"] == "member"
    assert wrong_password.status_code == 401


def test_non_admin_document_queries_are_owner_scoped():
    class Query:
        def __init__(self):
            self.clauses = []

        def filter(self, clause):
            self.clauses.append(clause)
            return self

    query = Query()
    db = SimpleNamespace(query=lambda model: query)
    member = SimpleNamespace(id=uuid4(), role="member")
    assert documents._document_query(db, member) is query
    assert len(query.clauses) == 1
    assert query.clauses[0].left.name == "owner_id"
    assert query.clauses[0].right.value == member.id


def test_admin_document_queries_use_role_scoped_override():
    class Query:
        filtered = False

        def filter(self, clause):
            self.filtered = True
            return self

    query = Query()
    db = SimpleNamespace(query=lambda model: query)
    admin = SimpleNamespace(id=uuid4(), role="admin")
    assert documents._document_query(db, admin) is query
    assert not query.filtered


def test_member_getting_another_users_document_returns_not_found():
    class Query:
        def __init__(self):
            self.clauses = []

        def filter(self, clause):
            self.clauses.append(clause)
            return self

        def first(self):
            return None

    query = Query()
    db = SimpleNamespace(query=lambda model: query)
    member = SimpleNamespace(id=uuid4(), role="member")
    with pytest.raises(HTTPException) as missing:
        documents._get_document(db, member, uuid4())
    assert missing.value.status_code == 404
    assert len(query.clauses) == 2
    assert query.clauses[0].left.name == "owner_id"


def test_document_storage_rejects_path_traversal(tmp_path):
    assert document_storage.resolve_legacy_file("../../outside.txt", tmp_path) is None


def test_document_download_returns_database_bytes_and_preserves_integrity(monkeypatch):
    document = SimpleNamespace(
        id=uuid4(), filename="policy.txt", content_type="text/plain", current_version=2
    )
    version = SimpleNamespace(id=uuid4())
    file_row = DocumentFile(version_id=version.id, content=b"original file bytes")

    class Query:
        def filter(self, *args):
            return self

        def first(self):
            return version

    db = SimpleNamespace(query=lambda model: Query(), get=lambda model, key: file_row)
    user = SimpleNamespace(id=uuid4(), role="member")
    def authorized_lookup(db_arg, user_arg, document_id):
        assert db_arg is db
        assert user_arg is user
        assert document_id == document.id
        return document

    monkeypatch.setattr(documents, "_get_document", authorized_lookup)
    monkeypatch.setattr(documents, "record_audit", lambda *args, **kwargs: None)

    response = documents.download_document(document.id, db, user)

    assert response.body == b"original file bytes"
    assert response.media_type == "text/plain"
    assert response.headers["content-disposition"].endswith("policy.txt")


def test_document_delete_uses_authorized_document_lookup_and_database_cascade(monkeypatch):
    document = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4(), role="member")
    calls = []

    class VersionQuery:
        def filter(self, *args):
            return self

        def delete(self, **kwargs):
            calls.append(("delete_versions", kwargs))

    db = SimpleNamespace(
        query=lambda model: VersionQuery(),
        delete=lambda row: calls.append(("delete", row)),
        commit=lambda: calls.append(("commit", None)),
        rollback=lambda: calls.append(("rollback", None)),
    )

    def authorized_lookup(db_arg, user_arg, document_id):
        assert db_arg is db
        assert user_arg is user
        assert document_id == document.id
        return document

    monkeypatch.setattr(documents, "_get_document", authorized_lookup)
    monkeypatch.setattr(documents, "record_audit", lambda *args, **kwargs: None)

    documents.delete_document(document.id, db, user)

    assert calls == [
        ("delete_versions", {"synchronize_session": False}),
        ("delete", document),
        ("commit", None),
    ]


def test_rate_limiter_blocks_after_configured_limit(monkeypatch):
    from redis.exceptions import RedisError

    monkeypatch.setenv("RATE_LIMIT_REDIS_REQUIRED", "false")
    monkeypatch.setattr(
        rate_limit,
        "get_redis_client",
        lambda: type("RedisDown", (), {
            "eval": lambda self, *args: (_ for _ in ()).throw(RedisError())
        })(),
    )
    scope = "test-" + str(uuid4())
    request = Request({"type": "http", "client": ("127.0.0.1", 1)})
    rate_limit.enforce_rate_limit(request, scope=scope, limit=1)
    with pytest.raises(HTTPException) as limited:
        rate_limit.enforce_rate_limit(request, scope=scope, limit=1)
    assert limited.value.status_code == 429


def test_distributed_rate_limiter_uses_atomic_shared_counter(monkeypatch):
    scope = "redis-test-" + str(uuid4())
    request = Request({"type": "http", "client": ("10.2.3.4", 1)})
    calls = []

    class FakeRedis:
        def eval(self, script, key_count, key, window):
            calls.append((script, key_count, key, window))
            return len(calls)

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: FakeRedis())
    rate_limit.enforce_rate_limit(request, scope=scope, limit=1)
    with pytest.raises(HTTPException) as limited:
        rate_limit.enforce_rate_limit(request, scope=scope, limit=1)
    assert limited.value.status_code == 429
    assert "10.2.3.4" not in calls[0][2]
    assert "INCR" in calls[0][0]


def test_rate_limiter_fails_closed_when_redis_is_required(monkeypatch):
    from redis.exceptions import RedisError

    monkeypatch.setenv("RATE_LIMIT_REDIS_REQUIRED", "true")

    class BrokenRedis:
        def eval(self, *args):
            raise RedisError("private connection detail")

    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: BrokenRedis())
    with pytest.raises(HTTPException) as unavailable:
        rate_limit.enforce_rate_limit(
            Request({"type": "http", "client": ("127.0.0.1", 2)}),
            scope="required-redis-test",
            limit=10,
        )
    assert unavailable.value.status_code == 503
    assert "private" not in unavailable.value.detail


def test_public_query_no_longer_accepts_owner_id_form_field():
    assert "owner_id" not in query_route.query_documents.__annotations__


def test_every_non_public_api_route_requires_authenticated_user():
    public_routes = {
        ("/api/v1/auth/register", "POST"),
        ("/api/v1/auth/token", "POST"),
    }
    api_routers = (
        documents.router,
        query_route.router,
        auth_route.router,
        feedback_route.router,
        audit_route.router,
    )
    protected_routes = [
        route
        for router in api_routers
        for route in router.routes
        if isinstance(route, APIRoute)
        and not all(
            (f"/api/v1{route.path}", method) in public_routes
            for method in route.methods
        )
    ]

    assert protected_routes
    for route in protected_routes:
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert auth.get_current_user in dependencies, (
            f"{route.path} must derive identity from the authenticated user"
        )


def test_query_identity_comes_from_bearer_token_not_form(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    user = SimpleNamespace(id=uuid4(), is_active=True, role="member")
    db = SimpleNamespace(get=lambda model, user_id: user)
    app = __import__("app.main", fromlist=["app"]).app
    captured = {}

    def fake_answer(db_arg, *, user_id, question, is_admin=False):
        captured.update(user_id=user_id, is_admin=is_admin, question=question)
        return {"answer": "ok"}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(query_route, "answer_question", fake_answer)
    token = auth.create_access_token(user.id)
    try:
        client = TestClient(app, base_url="http://localhost")
        unauthenticated = client.post(
            "/api/v1/query/", data={"question": "hello"}
        )
        response = client.post(
            "/api/v1/query/",
            data={"question": "hello", "owner_id": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.clear()
    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert captured == {
        "user_id": user.id,
        "is_admin": False,
        "question": "hello",
    }


def test_upload_uses_authenticated_owner_and_rejects_unauthenticated_request(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    user = SimpleNamespace(id=uuid4(), is_active=True, role="member")
    db = SimpleNamespace(
        get=lambda model, identifier: user if model is User and identifier == user.id else None
    )
    app = __import__("app.main", fromlist=["app"]).app
    captured = {}

    def fake_ingest(db_arg, *, owner_id, **kwargs):
        captured["owner_id"] = owner_id
        return {
            "document_id": str(uuid4()),
            "version_number": 1,
            "chunk_count": 1,
            "duplicate": False,
        }

    monkeypatch.setattr(documents, "ingest_document", fake_ingest)
    monkeypatch.setattr(documents, "enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(documents, "record_audit", lambda *args, **kwargs: None)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    token = auth.create_access_token(user.id)
    try:
        client = TestClient(app, base_url="http://localhost")
        anonymous = client.post(
            "/api/v1/documents/upload",
            files={"file": ("policy.txt", b"test", "text/plain")},
        )
        response = client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"owner_id": str(uuid4())},
            files={"file": ("policy.txt", b"test", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert anonymous.status_code == 401
    assert response.status_code == 201
    assert captured["owner_id"] == user.id
