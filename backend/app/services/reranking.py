import os
from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-base")


def _device() -> str | None:
    configured = os.getenv("RERANKER_DEVICE", "auto").strip().lower()
    if configured != "auto":
        return configured
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder(MODEL_NAME, device=_device())


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not query.strip() or not results:
        return []
    model = get_reranker()
    pairs = [(query, item["content"]) for item in results]
    batch_size = max(1, int(os.getenv("RERANKER_BATCH_SIZE", "8")))
    scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False)
    reranked = []
    for item, score in zip(results, scores):
        result = dict(item)
        result["reranker_score"] = float(score)
        reranked.append(result)
    reranked.sort(key=lambda item: item["reranker_score"], reverse=True)
    return reranked[:top_k]
