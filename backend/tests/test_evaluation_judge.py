import httpx
import pytest
from app.services import evaluation_judge

GOOD_JUDGMENT = {
    "answer_addresses_question": True,
    "claims_supported_by_evidence": True,
    "citation_entailment": True,
    "abstention_correct": False,
}


def test_judge_parses_only_required_boolean_fields():
    import json

    parsed = evaluation_judge.parse_judgment(json.dumps(GOOD_JUDGMENT))
    assert parsed == GOOD_JUDGMENT


@pytest.mark.parametrize(
    "content",
    ["not json", '{"answer_addresses_question": "yes"}', "[]"],
)
def test_judge_rejects_malformed_or_untyped_output(content):
    with pytest.raises(ValueError):
        evaluation_judge.parse_judgment(content)


def test_judge_rejects_non_text_output():
    with pytest.raises(TypeError, match="must be text"):
        evaluation_judge.parse_judgment(None)


def test_ollama_judge_explicitly_disables_thinking_and_uses_json(monkeypatch):
    captured = {}

    def mock_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:4b",
                "message": {"content": __import__("json").dumps(GOOD_JUDGMENT)},
            },
            request=httpx.Request("POST", evaluation_judge.OLLAMA_API_URL),
        )

    monkeypatch.setattr(evaluation_judge.httpx, "post", mock_post)
    result = evaluation_judge.judge_rag_answer(
        question="When must this be fixed?",
        answer="Before deployment [Source 1]",
        context="[Source 1] Critical issues must be resolved before deployment.",
        expected_answerable=True,
    )

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["json"]["think"] is False
    assert captured["json"]["stream"] is False
    assert captured["json"]["format"] == "json"
    assert result["citation_entailment"] is True
    assert result["model"] == "qwen3.5:4b"


def test_judge_timeout_returns_safe_error(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(
        evaluation_judge.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.TimeoutException("private fixture text")
        ),
    )
    with caplog.at_level(
        logging.WARNING, logger="app.services.evaluation_judge"
    ), pytest.raises(RuntimeError, match="unavailable"):
        evaluation_judge.judge_rag_answer(
            question="q", answer="a", context="private fixture text",
            expected_answerable=True,
        )
    assert "private fixture text" not in caplog.text
