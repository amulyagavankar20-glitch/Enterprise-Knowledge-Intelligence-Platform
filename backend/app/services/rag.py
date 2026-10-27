
import os
import re
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.services.reranking import rerank_results
from app.services.retrieval import hybrid_search

# Provisional threshold; calibrate using a larger evaluation dataset.
RERANKER_SCORE_THRESHOLD = float(os.getenv("RERANKER_SCORE_THRESHOLD", "0.001"))


def retrieve_context(
    db: Session,
    *,
    user_id: uuid.UUID,
    is_admin: bool = False,
    question: str,
    candidate_limit: int = 20,
    context_limit: int = 5,
) -> dict[str, Any]:
    question = question.strip()

    if not question:
        raise ValueError("Question must not be empty.")

    if len(question) > 4000:
        raise ValueError("Question must be 4000 characters or fewer.")

    if candidate_limit < 1 or context_limit < 1:
        raise ValueError("Retrieval limits must be positive.")

    hybrid_started = time.perf_counter()
    candidates = hybrid_search(
        db,
        user_id=user_id,
        is_admin=is_admin,
        query=question,
        candidate_limit=candidate_limit,
        result_limit=candidate_limit,
    )
    hybrid_search_ms = round((time.perf_counter() - hybrid_started) * 1000, 2)

    rerank_started = time.perf_counter()
    ranked = rerank_results(
        question,
        candidates,
        top_k=candidate_limit,
    )
    reranking_ms = round((time.perf_counter() - rerank_started) * 1000, 2)

    # Keep only results meeting the provisional relevance threshold.
    selection_started = time.perf_counter()
    relevant_ranked = [
        item
        for item in ranked
        if float(item["reranker_score"]) >= RERANKER_SCORE_THRESHOLD
    ]

    # Deduplicate identical content, keeping the highest-ranked result.
    unique_ranked = []
    seen_content = set()

    for item in relevant_ranked:
        normalized_content = " ".join(
            item["content"].split()
        ).casefold()

        if not normalized_content or normalized_content in seen_content:
            continue

        seen_content.add(normalized_content)
        unique_ranked.append(item)

        if len(unique_ranked) >= context_limit:
            break

    sources = [
        {
            "document_id": str(item["document_id"]),
            "document_title": item["document_title"],
            "filename": item["filename"],
            "chunk_index": item["chunk_index"],
            "reranker_score": float(item["reranker_score"]),
            "content": item["content"],
            "page_numbers": sorted({
                int(value) for value in re.findall(
                    r"\[Page\s+(\d+)\]", item["content"], re.IGNORECASE
                )
            }),
            "source_number": index,
        }
        for index, item in enumerate(unique_ranked, start=1)
    ]

    context = "\n\n".join(
        f"[Source {source['source_number']} — "
        f"{source['document_title']}, "
        f"chunk {source['chunk_index']}]\n"
        f"{source['content']}"
        for source in sources
    )
    context_selection_ms = round((time.perf_counter() - selection_started) * 1000, 2)

    return {
        "question": question,
        "context": context,
        "sources": sources,
        "retrieved_count": len(sources),
        "relevance_threshold": RERANKER_SCORE_THRESHOLD,
        "_timings_ms": {
            "hybrid_search_ms": hybrid_search_ms,
            "reranking_ms": reranking_ms,
            "context_selection_ms": context_selection_ms,
        },
    }
