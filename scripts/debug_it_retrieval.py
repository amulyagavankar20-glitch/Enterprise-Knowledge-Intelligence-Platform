
import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.database import SessionLocal
from app.services.retrieval import hybrid_search
from app.services.reranking import rerank_results

USER_ID = uuid.UUID(
    os.getenv(
        "RAG_EVAL_USER_ID",
        "af355322-852a-4753-857c-883d78d1999d",
    )
)
QUESTION = "What should employees do during a critical IT incident?"

with SessionLocal() as db:
    candidates = hybrid_search(
        db,
        user_id=USER_ID,
        query=QUESTION,
        candidate_limit=20,
        result_limit=20,
    )

    print(f"\nHybrid candidates: {len(candidates)}")
    for i, item in enumerate(candidates, 1):
        print(
            f"\n{i}. {item['document_title']} | "
            f"chunk={item['chunk_index']} | "
            f"RRF={item['rrf_score']:.5f}"
        )
        print(item["content"][:400])

    if candidates:
        ranked = rerank_results(QUESTION, candidates, top_k=20)
        print("\n--- RERANKED RESULTS ---")
        for i, item in enumerate(ranked, 1):
            print(
                f"\n{i}. {item['document_title']} | "
                f"score={item['reranker_score']:.6f}"
            )
            print(item["content"][:400])
