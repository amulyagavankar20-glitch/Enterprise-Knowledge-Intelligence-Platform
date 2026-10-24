import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.embeddings import embed_texts


def vector_search(
    db: Session,
    *,
    user_id: uuid.UUID,
    is_admin: bool = False,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query_vector = embed_texts([query])[0]

    statement = text("""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            dc.version_id,
            dc.chunk_index,
            dc.content,
            dc.metadata_json,
            d.title AS document_title,
            d.filename,
            1 - (dc.embedding <=> CAST(:embedding AS vector)) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN document_versions dv ON dv.id = dc.version_id
        WHERE (:is_admin OR d.owner_id = :user_id)
          AND d.status = 'completed'
          AND dv.status = 'completed'
          AND dv.version_number = d.current_version
          AND dc.embedding IS NOT NULL
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    rows = db.execute(
        statement,
        {
            "embedding": str(query_vector),
            "user_id": user_id,
            "is_admin": is_admin,
            "limit": limit,
        },
    ).mappings()

    return [dict(row) for row in rows]


def keyword_search(
    db: Session,
    *,
    user_id: uuid.UUID,
    is_admin: bool = False,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    statement = text("""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            dc.version_id,
            dc.chunk_index,
            dc.content,
            dc.metadata_json,
            d.title AS document_title,
            d.filename,
            ts_rank_cd(
                to_tsvector('english', dc.content),
                websearch_to_tsquery('english', :query)
            ) AS score
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN document_versions dv ON dv.id = dc.version_id
        WHERE (:is_admin OR d.owner_id = :user_id)
          AND d.status = 'completed'
          AND dv.status = 'completed'
          AND dv.version_number = d.current_version
          AND to_tsvector('english', dc.content)
              @@ websearch_to_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :limit
    """)

    rows = db.execute(
        statement,
        {
            "user_id": user_id,
            "is_admin": is_admin,
            "query": query,
            "limit": limit,
        },
    ).mappings()

    return [dict(row) for row in rows]


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    k: int = 60,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fuse ranked lists using reciprocal rank fusion."""
    scores: dict[str, float] = defaultdict(float)
    chunks: dict[str, dict[str, Any]] = {}

    for ranked_list in ranked_lists:
        seen_in_list: set[str] = set()

        for rank, item in enumerate(ranked_list, start=1):
            chunk_id = str(item["chunk_id"])

            if chunk_id in seen_in_list:
                continue

            seen_in_list.add(chunk_id)
            scores[chunk_id] += 1.0 / (k + rank)
            chunks.setdefault(chunk_id, item)

    results = []
    for chunk_id, item in chunks.items():
        result = dict(item)
        result["rrf_score"] = scores[chunk_id]
        results.append(result)

    results.sort(key=lambda item: item["rrf_score"], reverse=True)
    return results[:limit]


def hybrid_search(
    db: Session,
    *,
    user_id: uuid.UUID,
    is_admin: bool = False,
    query: str,
    candidate_limit: int = 20,
    result_limit: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve candidates from vector and keyword search, then fuse."""
    query = query.strip()
    if not query:
        raise ValueError("Query must not be empty.")

    vector_results = vector_search(
        db,
        user_id=user_id,
        is_admin=is_admin,
        query=query,
        limit=candidate_limit,
    )
    keyword_results = keyword_search(
        db,
        user_id=user_id,
        is_admin=is_admin,
        query=query,
        limit=candidate_limit,
    )

    return reciprocal_rank_fusion(
        [vector_results, keyword_results],
        limit=result_limit,
    )
