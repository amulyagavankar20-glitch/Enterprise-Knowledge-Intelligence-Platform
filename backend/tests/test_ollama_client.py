import json

import httpx
import pytest
from app.services import ollama_client


def make_response(status: int, body: str) -> httpx.Response:
    return httpx.Response(
        status,
        text=body,
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )


def test_transient_503_retries_with_exponential_backoff_then_succeeds(monkeypatch, caplog):
    caplog.set_level("INFO", logger="app.services.ollama_client")
    responses = [make_response(503, '{"error":"temporarily unavailable"}')]
    calls = []
    delays = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            response = responses[0]
            response.raise_for_status()
        return make_response(200, '{"message":{"content":"ok"}}')

    monkeypatch.setattr(ollama_client.httpx, "post", post)
    monkeypatch.setattr(ollama_client.time, "sleep", delays.append)
    result = ollama_client.post_chat(
        stage="answer_generation", url="http://127.0.0.1:11434/api/chat",
        payload={"model": "qwen3.5:4b", "messages": [{"role": "user", "content": "short prompt"}]},
        timeout_seconds=2, context_chars=0,
    )
    assert result.status_code == 200
    assert len(calls) == 2
    assert delays == [ollama_client.BACKOFF_SECONDS]
    assert caplog.records[-1].retry_count == 1


def test_permanent_bad_request_is_not_retried(monkeypatch, caplog):
    calls = []

    def post(*args, **kwargs):
        calls.append(1)
        return make_response(400, '{"error":"invalid request format"}')

    monkeypatch.setattr(ollama_client.httpx, "post", post)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda *_: pytest.fail("must not sleep"))
    with pytest.raises(httpx.HTTPStatusError):
        ollama_client.post_chat(
            stage="claim_verification", url="http://127.0.0.1:11434/api/chat",
            payload={"model": "qwen3.5:4b", "messages": []},
            timeout_seconds=1, context_chars=0,
        )
    assert len(calls) == 1
    record = caplog.records[-1]
    assert record.request_stage == "claim_verification"
    assert record.model == "qwen3.5:4b"
    assert record.http_status == 400
    assert record.retry_count == 0
    assert record.retrying is False


def test_transient_500_runner_error_is_retried_but_context_error_is_not(monkeypatch):
    calls = []

    def runner_error(*args, **kwargs):
        calls.append(1)
        response = make_response(500, '{"error":"model runner process has terminated"}')
        if len(calls) < 2:
            response.raise_for_status()
        return make_response(200, '{"message":{"content":"ok"}}')

    monkeypatch.setattr(ollama_client.httpx, "post", runner_error)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda *_: None)
    assert ollama_client.post_chat(
        stage="answer_generation", url="http://127.0.0.1:11434/api/chat",
        payload={"model": "qwen3.5:4b", "messages": []},
        timeout_seconds=1, context_chars=0,
    ).status_code == 200
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(
        ollama_client.httpx, "post",
        lambda *args, **kwargs: make_response(500, '{"error":"context length exceeded"}'),
    )
    with pytest.raises(httpx.HTTPStatusError):
        ollama_client.post_chat(
            stage="answer_generation", url="http://127.0.0.1:11434/api/chat",
            payload={"model": "qwen3.5:4b", "messages": []},
            timeout_seconds=1, context_chars=0,
        )


def test_timeout_retries_are_bounded_and_body_diagnostics_redact_prompt(caplog, monkeypatch):
    marker = "private document context marker"
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout(marker)

    monkeypatch.setattr(ollama_client.httpx, "post", timeout)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda *_: None)
    payload = {"model": "qwen3.5:4b", "messages": [{"role": "user", "content": marker}]}
    with pytest.raises(httpx.ReadTimeout):
        ollama_client.post_chat(
            stage="claim_verification", url="http://127.0.0.1:11434/api/chat",
            payload=payload, timeout_seconds=1, context_chars=len(marker),
        )
    assert len(calls) == ollama_client.MAX_ATTEMPTS
    assert marker not in caplog.text
    assert caplog.records[-1].retry_count == ollama_client.MAX_ATTEMPTS - 1


def test_error_body_summary_uses_safe_category_without_content():
    marker = "private claim text marker"
    response = make_response(500, json.dumps({"error": f"failed while processing {marker}"}))
    summary = ollama_client._response_error_detail(response)
    assert summary == "provider_error_redacted"
    assert marker not in summary
