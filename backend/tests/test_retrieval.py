from unittest.mock import Mock
from uuid import uuid4

from app.services import retrieval
from app.services.retrieval import reciprocal_rank_fusion


def test_rrf_combines_ranked_lists_and_deduplicates_chunk_ids():
    a = {"chunk_id": "a", "content": "A"}
    b = {"chunk_id": "b", "content": "B"}
    fused = reciprocal_rank_fusion([[a, b], [b, a]], k=0, limit=2)
    assert [item["chunk_id"] for item in fused] == ["a", "b"]
    assert fused[0]["rrf_score"] == fused[1]["rrf_score"]


def test_keyword_search_keeps_owner_and_current_version_filters():
    db = Mock()
    db.execute.return_value.mappings.return_value = []
    retrieval.keyword_search(
        db, user_id=uuid4(), query="critical incident", limit=20
    )
    statement = str(db.execute.call_args.args[0])
    assert "d.owner_id = :user_id" in statement
    assert "dv.version_number = d.current_version" in statement


def test_vector_search_keeps_owner_and_current_version_filters(monkeypatch):
    monkeypatch.setattr(retrieval, "embed_texts", lambda _: [[0.0] * 1024])
    db = Mock()
    db.execute.return_value.mappings.return_value = []
    retrieval.vector_search(db, user_id=uuid4(), query="Pune", limit=20)
    statement = str(db.execute.call_args.args[0])
    assert "d.owner_id = :user_id" in statement
    assert "dv.version_number = d.current_version" in statement


def test_hybrid_search_rejects_blank_query():
    try:
        retrieval.hybrid_search(
            Mock(), user_id=uuid4(), query="  "
        )
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("blank query was accepted")
