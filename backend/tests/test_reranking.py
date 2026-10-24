from app.services import reranking


class FakeCrossEncoder:
    def predict(self, pairs, batch_size, show_progress_bar):
        assert batch_size == 8
        assert show_progress_bar is False
        return [0.2, -0.4]


def test_reranker_sorts_by_score_and_preserves_input(monkeypatch):
    original = [
        {"content": "first"},
        {"content": "second"},
    ]
    monkeypatch.setattr(reranking, "get_reranker", lambda: FakeCrossEncoder())
    results = reranking.rerank_results("question", original, top_k=2)
    assert results[0]["content"] == "first"
    assert results[0]["reranker_score"] == 0.2
    assert "reranker_score" not in original[0]


def test_reranker_returns_empty_for_blank_question():
    assert reranking.rerank_results(" ", [{"content": "x"}]) == []
