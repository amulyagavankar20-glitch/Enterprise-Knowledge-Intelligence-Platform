from uuid import uuid4

import pytest
from app.services import reports


def test_report_contains_grounded_sections_and_only_existing_citations(monkeypatch):
    monkeypatch.setattr(
        reports,
        "answer_question",
        lambda *args, **kwargs: {
            "question": "When must security findings be resolved?",
            "answer": "Critical findings must be resolved before deployment. [Source 1]",
            "sources": [{
                "source_number": 1,
                "document_id": "doc-1",
                "filename": "security.txt",
                "document_title": "Security policy",
                "chunk_index": 2,
                "page_numbers": [4],
            }],
            "verification": {"status": "verified"},
        },
    )
    result = reports.generate_grounded_report(
        None, user_id=uuid4(), question="When must security findings be resolved?"
    )
    assert "## Executive summary" in result["markdown"]
    assert "## Key findings" in result["markdown"]
    assert "## Recommendations" in result["markdown"]
    assert "[Source 1]" in result["markdown"]
    assert "page 4" in result["markdown"]
    assert "## References" in result["markdown"]


def test_report_rejects_fabricated_citation(monkeypatch):
    monkeypatch.setattr(
        reports,
        "answer_question",
        lambda *args, **kwargs: {
            "question": "Q?",
            "answer": "Claim. [Source 9]",
            "sources": [{"source_number": 1}],
            "verification": {"status": "verified"},
        },
    )
    with pytest.raises(RuntimeError, match="citation"):
        reports.generate_grounded_report(None, user_id=uuid4(), question="Q?")


def test_report_withholds_verification_failure(monkeypatch):
    monkeypatch.setattr(
        reports,
        "answer_question",
        lambda *args, **kwargs: {"verification": {"status": "withheld"}},
    )
    with pytest.raises(RuntimeError, match="could not be verified"):
        reports.generate_grounded_report(None, user_id=uuid4(), question="Q?")
