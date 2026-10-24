from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIMENSION = 1024

@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)

def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_embedding_model()
    vectors = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    if vectors.shape[1] != EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Expected {EMBEDDING_DIMENSION} dimensions, "
            f"received {vectors.shape[1]}"
        )

    return vectors.tolist()


def count_tokens(text: str) -> int:
    """Count tokens with the same tokenizer used by BGE-large embeddings."""
    if not text:
        return 0
    model = get_embedding_model()
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        tokenizer = model._first_module().tokenizer
    return len(tokenizer.encode(text, add_special_tokens=False))
