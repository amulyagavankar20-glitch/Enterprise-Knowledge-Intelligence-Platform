"""Compatibility imports for the embedding service."""

from app.services.embeddings import (
    EMBEDDING_DIMENSION,
    MODEL_NAME,
    embed_texts,
    get_embedding_model,
)

__all__ = [
    "EMBEDDING_DIMENSION",
    "MODEL_NAME",
    "embed_texts",
    "get_embedding_model",
]
