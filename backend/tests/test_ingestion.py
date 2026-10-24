from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.db.models import Document, DocumentChunk, DocumentVersion, User
from app.services import ingestion
from app.services.extraction import extract_text


@pytest.mark.parametrize(
    "filename,content,match",
    [
        ("empty.txt", b"", "empty"),
        ("too-large.txt", None, "20 MB"),
    ],
)
def test_ingestion_rejects_empty_and_oversized_files(filename, content, match):
    if content is None:
        content = b"x" * (20 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match=match):
        ingestion.ingest_document(
            Mock(), owner_id=uuid4(), filename=filename, content=content
        )


def test_extraction_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text("payload.exe", b"text")


def test_duplicate_upload_returns_before_extraction_or_embedding(monkeypatch):
    owner_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    owner = SimpleNamespace(is_active=True)
    document = SimpleNamespace(
        id=document_id, title="Directory", filename="directory.txt", status="completed"
    )
    version = SimpleNamespace(id=version_id, document_id=document_id, version_number=1)
    version_query = Mock()
    version_query.join.return_value = version_query
    version_query.filter.return_value = version_query
    version_query.order_by.return_value = version_query
    version_query.first.return_value = version
    chunk_query = Mock()
    chunk_query.filter.return_value = chunk_query
    chunk_query.count.return_value = 3
    db = Mock()
    db.get.side_effect = [owner, document]
    db.query.side_effect = [version_query, chunk_query]
    monkeypatch.setattr(
        ingestion, "extract_text",
        lambda *args: (_ for _ in ()).throw(AssertionError("extracted duplicate")),
    )
    monkeypatch.setattr(
        ingestion, "embed_texts",
        lambda *args: (_ for _ in ()).throw(AssertionError("embedded duplicate")),
    )

    result = ingestion.ingest_document(
        db, owner_id=owner_id, filename="directory.txt", content=b"same bytes"
    )
    assert result["duplicate"] is True
    assert result["version_number"] == 1
    assert result["chunk_count"] == 3
    db.commit.assert_not_called()


def test_ingestion_rolls_back_failed_transaction(monkeypatch):
    owner_id = uuid4()
    owner = SimpleNamespace(is_active=True)
    version_query = Mock()
    version_query.join.return_value = version_query
    version_query.filter.return_value = version_query
    version_query.order_by.return_value = version_query
    version_query.first.return_value = None
    db = Mock()
    db.get.return_value = owner
    db.query.return_value = version_query
    monkeypatch.setattr(
        ingestion, "extract_text",
        lambda *args: (_ for _ in ()).throw(ValueError("bad document")),
    )
    with pytest.raises(ValueError, match="bad document"):
        ingestion.ingest_document(
            db, owner_id=owner_id, filename="bad.txt", content=b"input"
        )
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


class QueryChain:
    def __init__(self, first=None):
        self.first_value = first

    def join(self, *args):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.first_value


class IngestionSession:
    def __init__(self, owner, queries, *, fail_commit=False):
        self.owner = owner
        self.queries = iter(queries)
        self.added = []
        self.fail_commit = fail_commit
        self.committed = False
        self.rolled_back = False

    def get(self, model, identifier):
        if model is User:
            return self.owner
        return None

    def query(self, model):
        return next(self.queries)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("simulated commit failure")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def mock_ingestion_work(monkeypatch):
    monkeypatch.setattr(ingestion, "extract_text", lambda *_: "A source sentence.")
    monkeypatch.setattr(ingestion, "embed_texts", lambda chunks: [[0.0] * 1024 for _ in chunks])
    monkeypatch.setattr(ingestion, "count_tokens", lambda chunk: 4)


def test_new_ingestion_persists_original_and_token_count(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
    mock_ingestion_work(monkeypatch)
    owner = SimpleNamespace(is_active=True)
    db = IngestionSession(owner, [QueryChain(), QueryChain()])

    result = ingestion.ingest_document(
        db, owner_id=uuid4(), filename="source.txt", content=b"original bytes"
    )

    version = next(item for item in db.added if isinstance(item, DocumentVersion))
    chunk = next(item for item in db.added if isinstance(item, DocumentChunk))
    path = ingestion.Path(tmp_path) / version.storage_path
    assert result["version_number"] == 1
    assert path.read_bytes() == b"original bytes"
    assert chunk.token_count == 4
    assert db.committed


def test_changed_upload_creates_next_version_and_archives_previous(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
    mock_ingestion_work(monkeypatch)
    owner_id = uuid4()
    document = Document(
        id=uuid4(), owner_id=owner_id, title="Old", filename="source.txt",
        content_type="text/plain", status="completed", current_version=1,
        metadata_json={},
    )
    prior_version = SimpleNamespace(status="completed")
    db = IngestionSession(
        SimpleNamespace(is_active=True),
        [QueryChain(), QueryChain(document), QueryChain(prior_version)],
    )

    result = ingestion.ingest_document(
        db, owner_id=owner_id, filename="source.txt", content=b"new bytes"
    )

    assert result["version_number"] == 2
    assert document.current_version == 2
    assert prior_version.status == "archived"
    assert db.committed


def test_failed_commit_removes_new_original_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENT_STORAGE_DIR", str(tmp_path))
    mock_ingestion_work(monkeypatch)
    db = IngestionSession(
        SimpleNamespace(is_active=True),
        [QueryChain(), QueryChain()],
        fail_commit=True,
    )
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        ingestion.ingest_document(
            db, owner_id=uuid4(), filename="rollback.txt", content=b"temporary"
        )
    assert not list(tmp_path.rglob("rollback.txt"))
    assert db.rolled_back
