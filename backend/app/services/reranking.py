from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder


MODEL_NAME = "BAAI/bge-reranker-base"


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    # Let sentence-transformers select CUDA when available, otherwise CPU.
    return CrossEncoder(MODEL_NAME)


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not query.strip() or not results:
        return []

    model = get_reranker()
    pairs = [(query, item["content"]) for item in results]
    scores = model.predict(pairs, batch_size=8, show_progress_bar=False)

    reranked = []
    for item, score in zip(results, scores):
        result = dict(item)
        result["reranker_score"] = float(score)
        reranked.append(result)

    reranked.sort(
        key=lambda item: item["reranker_score"],
        reverse=True,
    )
    return reranked[:top_k]
