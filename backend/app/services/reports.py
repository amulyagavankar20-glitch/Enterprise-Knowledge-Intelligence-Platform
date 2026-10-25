"""Structured Markdown reports assembled from verified RAG answers."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.generation import ABSTENTION, answer_question


def generate_grounded_report(
    db: Session,
    *,
    user_id: UUID,
    is_admin: bool = False,
    question: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Build a report only from the ordinary authorized, verified answer path."""
    result = answer_question(
        db, user_id=user_id, is_admin=is_admin, question=question
    )
    verification = result.get("verification", {})
    if verification.get("status") == "withheld":
        raise RuntimeError("Report claims could not be verified against retrieved evidence.")
    if result.get("answer") != ABSTENTION and verification.get("status") != "verified":
        raise RuntimeError("Report generation requires enabled claim verification.")

    sources = result.get("sources", [])
    source_numbers = {int(source["source_number"]) for source in sources}
    cited_numbers = {
        int(number)
        for number in re.findall(r"\[Source\s+(\d+)\]", result.get("answer", ""), re.IGNORECASE)
    }
    if result.get("answer") != ABSTENTION and (
        not cited_numbers or not cited_numbers.issubset(source_numbers)
    ):
        raise RuntimeError("Report citations did not pass source validation.")

    report_title = (title or "").strip()[:180] or f"Knowledge report: {question.strip()}"
    report_title = report_title[:180]
    answer = result.get("answer") or ABSTENTION
    findings = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", answer)
        if part.strip() and part.strip() != ABSTENTION
    ]
    if answer == ABSTENTION:
        findings = ["The accessible documents did not provide enough evidence to answer reliably."]

    references = []
    for source in sources:
        number = int(source["source_number"])
        if number not in cited_numbers:
            continue
        filename = source.get("filename") or "Source document"
        pages = source.get("page_numbers") or []
        page_reference = (
            "page " + ", ".join(str(page) for page in pages)
            if pages else "page reference unavailable"
        )
        references.append(
            f"- [Source {number}] {filename} — {source.get('document_title') or filename}; "
            f"chunk {source.get('chunk_index', 'unknown')}, {page_reference}."
        )

    recommendations = [
        finding for finding in findings
        if re.search(r"\b(?:must|should|required|ensure|prohibited)\b", finding, re.IGNORECASE)
    ]
    recommendation_lines = (
        "\n".join(f"- {recommendation}" for recommendation in recommendations)
        if recommendations
        else "- No recommendations were added beyond the retrieved source statements."
    )
    markdown = "\n".join([
        f"# {report_title}",
        "",
        "## Purpose",
        question.strip(),
        "",
        "## Executive summary",
        answer,
        "",
        "## Key findings",
        *[f"- {finding}" for finding in findings],
        "",
        "## Evidence-backed analysis",
        answer,
        "",
        "## Risks, gaps, or contradictions",
        ("- Insufficient evidence was found; treat this report as incomplete." if answer == ABSTENTION else "- No source conflict was established by this answer. The system does not independently prove that the retrieved material is complete."),
        "",
        "## Recommendations",
        "Recommendations below repeat source-backed requirements; they are not new policy: ",
        recommendation_lines,
        "",
        "## References",
        *(references or ["- No cited source was available."]),
        "",
        "## Verification note",
        f"Claim check status: `{verification.get('status', 'unknown')}`. Model-assisted support checks are estimates, not proof of factual correctness. Citations identify retrieved sources but do not alone prove entailment.",
    ])
    return {
        "title": report_title,
        "question": result.get("question", question),
        "markdown": markdown,
        "sources": sources,
        "verification": verification,
        "export_formats": ["markdown", "browser_print_to_pdf"],
    }
