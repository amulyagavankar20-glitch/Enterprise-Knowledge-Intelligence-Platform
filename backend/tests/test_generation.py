import logging

import httpx
import pytest

from app.services import generation


def provider_response(content, model="test-model"):
    return httpx.Response(
        200,
        json={"model": model, "choices": [{"message": {"content": content}}]},
        request=httpx.Request("POST", generation.API_URL),
    )


def setup_key(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-key")


def ollama_response(content, model="qwen3.5:4b", thinking=None):
    return httpx.Response(
        200,
        json={
            "model": model,
            "message": {"role": "assistant", "content": content, "thinking": thinking},
            "done": True,
        },
        request=httpx.Request("POST", generation.OLLAMA_API_URL),
    )


def test_generation_removes_invalid_citation_labels(monkeypatch):
    setup_key(monkeypatch)
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: provider_response(
            "Rahul is in Pune. [Source 1] [Source 9]"
        ),
    )
    answer, model = generation.generate_answer("Where?", "context", {1})
    assert answer == "Rahul is in Pune. [Source 1]"
    assert model == "test-model"


def test_generation_rejects_answer_without_valid_citation(monkeypatch):
    setup_key(monkeypatch)
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: provider_response(
            "The answer is in the document. [Source 8]"
        ),
    )
    with pytest.raises(RuntimeError, match="lacked a valid source citation"):
        generation.generate_answer("q", "context", {1})


@pytest.mark.parametrize("label", ["User Safety: safe", "User Safety: unsafe"])
def test_generation_rejects_safety_classification(monkeypatch, label):
    setup_key(monkeypatch)
    monkeypatch.setattr(
        generation.httpx, "post", lambda *args, **kwargs: provider_response(label)
    )
    with pytest.raises(RuntimeError, match="did not return an answer"):
        generation.generate_answer("q", "context", {1})


def test_generation_rejects_malformed_json(monkeypatch):
    setup_key(monkeypatch)
    response = httpx.Response(
        200, content=b"not json", request=httpx.Request("POST", generation.API_URL)
    )
    monkeypatch.setattr(generation.httpx, "post", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="invalid response"):
        generation.generate_answer("q", "context", {1})


@pytest.mark.parametrize("content", [None, "", "   "])
def test_generation_rejects_empty_content(monkeypatch, content):
    setup_key(monkeypatch)
    monkeypatch.setattr(
        generation.httpx, "post", lambda *args, **kwargs: provider_response(content)
    )
    with pytest.raises(RuntimeError, match="empty answer"):
        generation.generate_answer("q", "context", {1})


def test_http_error_logs_status_without_provider_body(monkeypatch, caplog):
    setup_key(monkeypatch)
    request = httpx.Request("POST", generation.API_URL)
    response = httpx.Response(429, text="private context marker", request=request)
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.HTTPStatusError("provider failure", request=request, response=response)
        ),
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="HTTP 429"):
            generation.generate_answer("q", "context", {1})
    assert "429" in caplog.text
    assert "private context marker" not in caplog.text


def test_timeout_is_reported_without_exception_text(monkeypatch, caplog):
    setup_key(monkeypatch)
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.TimeoutException("private context marker")
        ),
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="Could not connect"):
            generation.generate_answer("q", "context", {1})
    assert "private context marker" not in caplog.text


def test_answer_question_abstains_without_provider_call(monkeypatch):
    monkeypatch.setattr(
        generation, "retrieve_context",
        lambda *args, **kwargs: {
            "question": "unknown?", "context": "", "sources": []
        },
    )
    monkeypatch.setattr(
        generation, "generate_answer",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("called")),
    )
    result = generation.answer_question(None, user_id=None, question="unknown?")
    assert result["answer"] == generation.ABSTENTION
    assert result["sources"] == []
    assert result["model"] is None


def test_ollama_uses_local_chat_endpoint_and_disables_thinking(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
    calls = {}

    def mock_post(url, **kwargs):
        calls.update(url=url, **kwargs)
        return ollama_response("Rahul works in Pune. [Source 1]", thinking="hidden trace")

    monkeypatch.setattr(generation.httpx, "post", mock_post)
    answer, model = generation.generate_answer("Where?", "context", {1})

    assert calls["url"] == "http://127.0.0.1:11434/api/chat"
    assert calls["json"]["model"] == "qwen3.5:4b"
    assert calls["json"]["think"] is False
    assert calls["json"]["stream"] is False
    assert answer == "Rahul works in Pune. [Source 1]"
    assert model == "qwen3.5:4b"


def test_ollama_timeout_is_reported_safely(monkeypatch, caplog):
    monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.TimeoutException("private context marker")
        ),
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="Could not connect to Ollama"):
            generation.generate_answer("q", "context", {1})
    assert "private context marker" not in caplog.text


def test_ollama_rejects_malformed_response(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
    malformed = httpx.Response(
        200, json={"model": "qwen3.5:4b"},
        request=httpx.Request("POST", generation.OLLAMA_API_URL),
    )
    monkeypatch.setattr(generation.httpx, "post", lambda *args, **kwargs: malformed)
    with pytest.raises(RuntimeError, match="unexpected response"):
        generation.generate_answer("q", "context", {1})


def test_ollama_rejects_empty_content_even_if_thinking_exists(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: ollama_response("", thinking="reasoning only"),
    )
    with pytest.raises(RuntimeError, match="empty answer"):
        generation.generate_answer("q", "context", {1})


def test_ollama_requires_valid_source_citation(monkeypatch):
    monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
    monkeypatch.setattr(
        generation.httpx, "post",
        lambda *args, **kwargs: ollama_response("Evidence says Pune. [Source 2]"),
    )
    with pytest.raises(RuntimeError, match="lacked a valid source citation"):
        generation.generate_answer("Where?", "context", {1})


def test_generation_prompt_preserves_specific_procedure_terms():
    messages = generation._messages("What review?", "Submit code through a pull request.")
    system_prompt = messages[0]["content"].casefold()
    assert "pull request" in system_prompt
    assert "each required step" in system_prompt
