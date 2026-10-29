import json

import asyncio

import pytest

from scripts import evaluate_ragas
from scripts.evaluate_ragas import _load_results


def test_ragas_loader_requires_versioned_evaluation_dataset(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"results": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="unversioned"):
        _load_results(path)


def test_ragas_loader_accepts_expected_dataset_version(tmp_path):
    path = tmp_path / "v1.json"
    path.write_text(json.dumps({"dataset_id": "enterprise-rag-v1", "dataset_version": 1, "results": []}), encoding="utf-8")
    assert _load_results(path)["dataset_version"] == 1


def test_ragas_rows_exclude_unsupported_and_malformed_samples():
    rows = evaluate_ragas._evaluation_rows({"results": [
        {"question": "Q", "answer": "A", "retrieved_contexts": ["evidence"], "reference_answer_approximate": "R"},
        {"question": "Q2", "answer": "A2", "retrieved_contexts": [], "reference_answer_approximate": "R2"},
        {"question": "Q3", "answer": "abstain", "retrieved_contexts": [], "reference_answer_approximate": "R3"},
    ]})
    assert len(rows) == 1
    assert rows[0]["case_index"] == 1
    assert rows[0]["user_input"] == "Q"


def test_ragas_rows_exclude_failed_cases_from_partial_runs():
    base = {
        "question": "Q", "answer": "A", "retrieved_contexts": ["evidence"],
        "reference_answer_approximate": "R",
    }
    rows = evaluate_ragas._evaluation_rows({"results": [
        {**base, "case_status": "completed"},
        {**base, "case_status": "failed", "failure_stage": "verification"},
    ]})
    assert len(rows) == 1
    assert rows[0]["case_index"] == 1


def test_ragas_run_failure_is_machine_readable_and_carries_no_payload(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise ModuleNotFoundError("private import detail")

    monkeypatch.setattr(evaluate_ragas, "_score_run", fail)
    result = evaluate_ragas._score_run_safely(
        {"dataset_id": "enterprise-rag-v1", "dataset_version": 1, "results": []},
        "improved", tmp_path / "result.json",
    )
    assert result["failure"] == {"category": "ModuleNotFoundError"}
    assert all(score is None for score in result["scores"].values())
    assert "private import detail" not in json.dumps(result)
    assert evaluate_ragas._has_scoring_failure([result]) is True


def test_ragas_completed_scores_are_not_marked_failed():
    run = {"scores": {name: 0.5 for name in evaluate_ragas.METRICS}, "metric_failure_count": 0}
    assert evaluate_ragas._has_scoring_failure([run]) is False


def test_ragas_llm_uses_local_openai_compatible_ollama_endpoint():
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

    def fake_factory(model, **kwargs):
        captured["factory"] = {"model": model, **kwargs}
        return "ragas-llm"

    llm, client = evaluate_ragas._make_local_ollama_ragas_llm(
        "qwen3.5:4b",
        "http://127.0.0.1:11434",
        client_class=FakeAsyncClient,
        ragas_llm_factory=fake_factory,
    )

    assert llm == "ragas-llm"
    assert isinstance(client, FakeAsyncClient)
    assert captured["client"] == {
        "api_key": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
    }
    assert captured["factory"] == {
        "model": "qwen3.5:4b",
        "provider": "openai",
        "client": client,
        "reasoning_effort": "none",
    }


def test_ragas_llm_rejects_non_loopback_endpoint():
    with pytest.raises(ValueError, match="local loopback"):
        evaluate_ragas._make_local_ollama_ragas_llm(
            "qwen3.5:4b",
            "https://example.invalid/v1",
            client_class=object,
            ragas_llm_factory=lambda *args, **kwargs: None,
        )


def test_ragas_metric_receives_only_its_declared_fields():
    captured = {}

    class AnswerRelevancyLikeMetric:
        async def ascore(self, user_input: str, response: str):
            captured["values"] = (user_input, response)
            return "score"

    row = {
        "user_input": "question",
        "response": "answer",
        "retrieved_contexts": ["context"],
        "reference": "reference",
    }

    result = asyncio.run(evaluate_ragas._score_metric(AnswerRelevancyLikeMetric(), row))

    assert result == "score"
    assert captured["values"] == ("question", "answer")
