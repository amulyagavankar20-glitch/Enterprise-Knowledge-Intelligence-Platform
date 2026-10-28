import os
from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))


def _device() -> str | None:
    configured = os.getenv("EMBEDDING_DEVICE", "auto").strip().lower()
    if configured != "auto":
        return configured
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    # Load once per process. Use EMBEDDING_MODEL_NAME to test a fine-tuned model.
    return SentenceTransformer(MODEL_NAME, device=_device())


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_embedding_model()
    batch_size = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", "16")))
    vectors = model.encode(
        texts, batch_size=batch_size, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    )
    if vectors.shape[1] != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Expected {EMBEDDING_DIMENSION} dimensions for {MODEL_NAME}, "
            f"received {vectors.shape[1]}. Set EMBEDDING_DIMENSION correctly and "
            "re-embed all stored chunks when changing encoder models."
        )
    return vectors.tolist()


def count_tokens(text: str) -> int:
    """Count tokens with the same tokenizer used by the active embedding model."""
    if not text:
        return 0
    model = get_embedding_model()
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        tokenizer = model._first_module().tokenizer
    return len(tokenizer.encode(text, add_special_tokens=False))
