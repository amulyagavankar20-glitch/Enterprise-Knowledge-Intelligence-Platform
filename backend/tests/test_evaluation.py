import evaluate_rag
from app.services.rag import RERANKER_SCORE_THRESHOLD
from evaluate_rag import (
    TEST_CASES,
    answer_looks_like_abstention,
    completed_cases,
    evaluate_case,
    evaluate_thresholds,
    fact_coverage,
    normalize_fact,
    verification_is_operational_failure,
)
from setup_test_data import (
    answer_looks_like_abstention as smoke_answer_looks_like_abstention,
)


def test_fact_normalization_handles_space_and_punctuation_variants():
    assert normalize_fact("IT on-call team") == normalize_fact("IT oncall team")
    assert normalize_fact("department-manager") == normalize_fact("department manager")


def test_abstention_classifier_recognizes_clear_declines():
    assert answer_looks_like_abstention(
        "The directory does not include a CEO phone number, so I cannot provide it."
    )
    assert not answer_looks_like_abstention("The CEO is Aditi Sharma.")


def test_abstention_classifier_recognizes_saved_failed_case():
    answer = (
        "The provided document does not contain the CEO's personal phone number. "
        "It does not identify a CEO or provide personal contact information."
    )
    assert answer_looks_like_abstention(answer)
    assert smoke_answer_looks_like_abstention(answer)


def test_fact_coverage_separates_partial_from_complete_answers():
    facts = ["pull request", "one engineer", "approve"]
    answer = "At least one engineer must review and approve the change."
    assert fact_coverage(answer, facts) == 2 / 3


def test_saved_policy_failure_requires_specific_procedure_term(monkeypatch):
    case = next(
        item for item in TEST_CASES
        if item["question"] == "What review is required before production code can be released?"
    )
    monkeypatch.setattr(
        evaluate_rag, "retrieve_context",
        lambda *args, **kwargs: {
            "question": case["question"],
            "context": "At least one engineer must review and approve the pull request.",
            "sources": [{
                "source_number": 1,
                "filename": case["source"],
                "content": "At least one engineer must review and approve the pull request.",
            }],
        },
    )
    monkeypatch.setattr(
        evaluate_rag, "generate_answer",
        lambda *args, **kwargs: (
            "At least one engineer must review and approve the change [Source 1].",
            "qwen3.5:4b",
        ),
    )
    monkeypatch.setattr(
        evaluate_rag,
        "answer_question",
        lambda *args, **kwargs: {
            "answer": "At least one engineer must review and approve the change [Source 1].",
            "model": "qwen3.5:4b",
            "verification": {"status": "verified"},
        },
    )
    row = evaluate_case(None, case)
    assert row["answer_expected_facts_matched_count"] == 2
    assert row["answer_expected_fact_coverage_approximate"] == 2 / 3
    assert row["answer_expected_facts_complete_approximate"] is False
    assert row["passed"] is False


def test_unsupported_retrieved_context_can_still_be_correctly_abstained(monkeypatch):
    question = "What is the CEO's personal phone number?"
    case = next(item for item in TEST_CASES if item["question"] == question)
    monkeypatch.setattr(
        evaluate_rag, "retrieve_context",
        lambda *args, **kwargs: {
            "question": question,
            "context": "Employee directory has no CEO phone number.",
            "sources": [{
                "source_number": 1,
                "filename": "employee_directory.txt",
                "content": "Employee directory has no CEO phone number.",
                "reranker_score": 0.001742,
            }],
        },
    )
    monkeypatch.setattr(
        evaluate_rag, "generate_answer",
        lambda *args, **kwargs: (
            "The document does not contain the CEO's personal phone number [Source 1].",
            "qwen3.5:4b",
        ),
    )
    monkeypatch.setattr(
        evaluate_rag,
        "answer_question",
        lambda *args, **kwargs: {
            "answer": "The document does not contain the CEO's personal phone number [Source 1].",
            "model": "qwen3.5:4b",
            "verification": {"status": "abstained"},
        },
    )
    row = evaluate_case(None, case)
    assert row["retrieval_success_at_k"] is None
    assert row["unsupported_retrieval_empty"] is False
    assert row["abstention_correct"] is True
    assert row["passed"] is True


def test_threshold_sweep_uses_answerable_and_unsupported_labels():
    rows = [
        {
            "question": "answerable",
            "expected_source_label": "policy.txt",
            "source_scores": [{"filename": "policy.txt", "reranker_score": RERANKER_SCORE_THRESHOLD}],
        },
        {
            "question": "unsupported",
            "expected_source_label": None,
            "source_scores": [],
        },
    ]
    sweep = evaluate_thresholds(rows)
    current = next(
        row for row in sweep if row["threshold"] == RERANKER_SCORE_THRESHOLD
    )
    high = next(row for row in sweep if row["threshold"] > RERANKER_SCORE_THRESHOLD)
    assert current["answerable_recall_at_5"] == 1.0
    assert current["unsupported_empty_retrieval_rate"] == 1.0
    assert high["answerable_recall_at_5"] == 0.0


def test_completed_case_filter_excludes_failed_rows_from_metrics():
    rows = [
        {"case_status": "completed", "passed": True},
        {"case_status": "failed", "failure_stage": "verification"},
        {"case_status": "failed", "failure_stage": "answer_generation"},
    ]
    assert completed_cases(rows) == [rows[0]]


def test_retrieval_failure_is_labeled_without_fabricating_metric_values(monkeypatch):
    case = TEST_CASES[0]
    monkeypatch.setattr(
        evaluate_rag, "retrieve_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private db detail")),
    )
    row = evaluate_case(None, case)
    assert row["case_status"] == "failed"
    assert row["failure_stage"] == "retrieval"
    assert row["failure_category"] == "RuntimeError"
    assert "private db detail" not in str(row)


def test_verifier_transport_failure_is_operational_but_claim_rejection_is_scored():
    assert verification_is_operational_failure({
        "status": "withheld", "failure_category": "ollama_http_error",
    })
    assert not verification_is_operational_failure({
        "status": "withheld", "failure_category": "unsupported_or_contradicted_claims",
    })
