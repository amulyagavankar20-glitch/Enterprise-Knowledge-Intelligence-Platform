"""Local Ollama HTTP calls with bounded transient retries and safe diagnostics."""

import logging
import json
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 0.25
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 502, 503, 504}
TRANSIENT_500_CATEGORIES = {
    "runner_terminated", "temporarily_unavailable", "server_overloaded",
    "connection_reset", "internal_server_error",
}


def post_chat(
    *,
    stage: str,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    context_chars: int,
) -> httpx.Response:
    """POST once or retry a transient Ollama failure at most twice."""
    messages = payload.get("messages", [])
    prompt_chars = sum(
        len(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("content"), str)
    )
    retry_count = 0
    while True:
        started = time.perf_counter()
        try:
            response = httpx.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            if retry_count:
                fields = _diagnostic_fields(
                    stage, payload, prompt_chars, context_chars,
                    time.perf_counter() - started, retry_count,
                    response.status_code,
                )
                logger.info(
                    "ollama_request_recovered %s",
                    json.dumps(fields, sort_keys=True, separators=(",", ":")),
                    extra=fields,
                )
            response.extensions["ollama_request_diagnostics"] = _diagnostic_fields(
                stage, payload, prompt_chars, context_chars,
                time.perf_counter() - started, retry_count,
                response.status_code,
            )
            return response
        except httpx.HTTPStatusError as exc:
            response = exc.response
            transient = _transient_status(response)
            _log_failure(
                stage, payload, prompt_chars, context_chars,
                time.perf_counter() - started, retry_count,
                status_code=response.status_code,
                response=response,
                retrying=transient and retry_count < MAX_ATTEMPTS - 1,
            )
            if not transient or retry_count >= MAX_ATTEMPTS - 1:
                raise
        except httpx.RequestError as exc:
            transient = not isinstance(exc, (httpx.InvalidURL, httpx.UnsupportedProtocol))
            _log_failure(
                stage, payload, prompt_chars, context_chars,
                time.perf_counter() - started, retry_count,
                error_type=type(exc).__name__,
                retrying=transient and retry_count < MAX_ATTEMPTS - 1,
            )
            if not transient or retry_count >= MAX_ATTEMPTS - 1:
                raise

        time.sleep(BACKOFF_SECONDS * (2 ** retry_count))
        retry_count += 1


def _transient_status(response: httpx.Response) -> bool:
    if response.status_code in TRANSIENT_HTTP_STATUSES:
        return True
    if response.status_code != 500:
        return False
    return _response_error_detail(response) in TRANSIENT_500_CATEGORIES


def _log_failure(
    stage: str,
    payload: dict[str, Any],
    prompt_chars: int,
    context_chars: int,
    elapsed_seconds: float,
    retry_count: int,
    *,
    status_code: int | None = None,
    response: httpx.Response | None = None,
    error_type: str | None = None,
    retrying: bool,
) -> None:
    fields = _diagnostic_fields(
        stage, payload, prompt_chars, context_chars, elapsed_seconds,
        retry_count, status_code,
    )
    fields.update({
        "error_type": error_type,
        "response_body_chars": len(response.content) if response is not None else None,
        "response_body_summary": (
            _response_error_detail(response) if response is not None else None
        ),
        "retrying": retrying,
    })
    logger.warning(
        "ollama_request_failed %s",
        json.dumps(fields, sort_keys=True, separators=(",", ":")),
        extra=fields,
    )


def log_invalid_response(
    *,
    stage: str,
    payload: dict[str, Any],
    response: httpx.Response,
    context_chars: int,
    error_type: str,
) -> None:
    """Log response diagnostics while never logging generated text or evidence."""
    fields = dict(response.extensions.get("ollama_request_diagnostics", {}))
    if not fields:
        messages = payload.get("messages", [])
        prompt_chars = sum(
            len(message.get("content", ""))
            for message in messages
            if isinstance(message, dict) and isinstance(message.get("content"), str)
        )
        fields = _diagnostic_fields(
            stage, payload, prompt_chars, context_chars,
            response.elapsed.total_seconds(), 0, response.status_code,
        )
    response_data = None
    try:
        response_data = response.json()
    except ValueError:
        pass
    content = None
    message = response_data.get("message") if isinstance(response_data, dict) else None
    if isinstance(message, dict):
        content = message.get("content")
    body_summary = _content_error_category(content)
    if isinstance(response_data, dict) and response_data.get("done_reason") == "length":
        body_summary = "output_token_limit"
    fields.update({
        "error_type": error_type,
        "response_body_chars": len(response.content),
        "response_content_chars": len(content) if isinstance(content, str) else None,
        "response_body_summary": body_summary,
        "done_reason": response_data.get("done_reason") if isinstance(response_data, dict) else None,
        "eval_count": response_data.get("eval_count") if isinstance(response_data, dict) else None,
        "prompt_eval_count": response_data.get("prompt_eval_count") if isinstance(response_data, dict) else None,
    })
    logger.warning(
        "ollama_invalid_response %s",
        json.dumps(fields, sort_keys=True, separators=(",", ":")),
        extra=fields,
    )


def _content_error_category(content: Any) -> str:
    if not isinstance(content, str) or not content.strip():
        return "empty_message_content"
    try:
        value = json.loads(content)
    except ValueError:
        return "malformed_json_content"
    if not isinstance(value, dict):
        return "json_root_not_object"
    results = value.get("results")
    if results is None:
        return "expected_results_missing"
    if not isinstance(results, list):
        return "results_not_array"
    if any(not isinstance(item, dict) for item in results):
        return "result_item_not_object"
    expected_keys = {
        "claim_id", "supported", "contradicted", "supporting_source_numbers",
    }
    if any(set(item) != expected_keys for item in results):
        return "result_schema_mismatch"
    return "valid_json_schema_shape"


def _diagnostic_fields(
    stage: str,
    payload: dict[str, Any],
    prompt_chars: int,
    context_chars: int,
    elapsed_seconds: float,
    retry_count: int,
    status_code: int | None,
) -> dict[str, Any]:
    return {
        "provider": "ollama",
        "request_stage": stage,
        "model": payload.get("model"),
        "prompt_chars": prompt_chars,
        "prompt_tokens_estimate_chars_div_4": round(prompt_chars / 4),
        "context_chars": context_chars,
        "context_tokens_estimate_chars_div_4": round(context_chars / 4),
        "elapsed_ms": round(elapsed_seconds * 1000, 2),
        "retry_count": retry_count,
        "http_status": status_code,
    }


def _response_error_detail(response: httpx.Response) -> str:
    """Return only a safe category for the provider's error body."""
    try:
        body = response.json()
    except ValueError:
        return "non_json_error_response"
    if not isinstance(body, dict) or not isinstance(body.get("error"), str):
        return "json_error_response_without_error_field"
    detail = body["error"].casefold()
    categories = (
        (r"out of memory|memory allocation|not enough memory|cuda.*memory", "resource_exhaustion"),
        (r"context length|context window|too many tokens|num_ctx", "context_limit"),
        (r"invalid request|malformed|unsupported parameter|does not support", "invalid_request"),
        (r"model .*not found", "model_not_found"),
        (r"runner process.*(terminated|stopped|exited)", "runner_terminated"),
        (r"temporarily unavailable", "temporarily_unavailable"),
        (r"server is overloaded", "server_overloaded"),
        (r"connection reset by peer", "connection_reset"),
        (r"internal server error", "internal_server_error"),
    )
    for pattern, category in categories:
        if re.search(pattern, detail):
            return category
    return "provider_error_redacted"
