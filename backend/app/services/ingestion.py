
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentVersion, User
from app.services.chunking import chunk_text
from app.services.document_storage import persist_original, remove_original
from app.services.embeddings import count_tokens, embed_texts
from app.services.extraction import extract_text

logger = logging.getLogger(__name__)


def ingest_document(
    db: Session,
    *,
    owner_id: uuid.UUID,
    filename: str,
    content: bytes,
    title: str | None = None,
    content_type: str | None = None,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> dict[str, Any]:
    """Extract, chunk, embed, and persist one document atomically."""

    if not content:
        raise ValueError("Uploaded file is empty.")

    if len(content) > 20 * 1024 * 1024:
        raise ValueError("File exceeds the 20 MB limit.")

    safe_filename = Path(filename).name
    if not safe_filename or len(safe_filename) > 500:
        raise ValueError("Invalid filename.")

    checksum = hashlib.sha256(content).hexdigest()

    stored_path: str | None = None
    try:
        # Validate the owner before processing the file.
        owner = db.get(User, owner_id)
        if owner is None or not owner.is_active:
            raise ValueError("Owner does not exist or is inactive.")

        # Prevent duplicate uploads by the same user.
        existing_version = (
            db.query(DocumentVersion)
            .join(
                Document,
                DocumentVersion.document_id == Document.id,
            )
            .filter(
                Document.owner_id == owner_id,
                DocumentVersion.checksum == checksum,
                DocumentVersion.status.in_(["completed", "archived"]),
                Document.status == "completed",
            )
            .order_by(DocumentVersion.created_at.desc())
            .first()
        )

        if existing_version:
            existing_document = db.get(
                Document, existing_version.document_id
            )

            if existing_document is not None:
                chunk_count = (
                    db.query(DocumentChunk)
                    .filter(
                        DocumentChunk.version_id == existing_version.id
                    )
                    .count()
                )

                return {
                    "document_id": str(existing_document.id),
                    "version_id": str(existing_version.id),
                    "title": existing_document.title,
                    "filename": existing_document.filename,
                    "status": existing_document.status,
                    "version_number": existing_version.version_number,
                    "chunk_count": chunk_count,
                    "checksum": checksum,
                    "duplicate": True,
                    "message": (
                        "Identical file already exists for this user. "
                        "No new document was created."
                    ),
                }

        # Extract text and split it into chunks.
        text = extract_text(safe_filename, content)
        chunks = chunk_text(
            text,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        if not chunks:
            raise ValueError("Document contains no usable text.")

        # Generate embeddings.
        vectors = embed_texts(chunks)

        if len(vectors) != len(chunks):
            raise RuntimeError(
                "Embedding count does not match chunk count."
            )
        token_counts = [count_tokens(chunk) for chunk in chunks]

        # Re-uploading changed content under the same name creates a new
        # version. Identical bytes returned above without re-embedding.
        document = (
            db.query(Document)
            .filter(
                Document.owner_id == owner_id,
                Document.filename == safe_filename,
                Document.status == "completed",
            )
            .order_by(Document.created_at.desc())
            .with_for_update()
            .first()
        )
        if document is None:
            document = Document(
                owner_id=owner_id,
                title=(title or safe_filename)[:500],
                filename=safe_filename,
                content_type=content_type or "application/octet-stream",
                status="processing",
                current_version=1,
                metadata_json={
                    "file_size_bytes": len(content),
                    "sha256": checksum,
                    "chunk_count": len(chunks),
                },
            )
            db.add(document)
            db.flush()
            version_number = 1
        else:
            version_number = document.current_version + 1
            previous_version = (
                db.query(DocumentVersion)
                .filter(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_number == document.current_version,
                )
                .first()
            )
            if previous_version is None:
                raise RuntimeError("Current document version is missing.")
            previous_version.status = "archived"
            document.status = "processing"

        stored_path = persist_original(
            document_id=document.id,
            version_number=version_number,
            filename=safe_filename,
            content=content,
        )
        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            checksum=checksum,
            storage_path=stored_path,
            status="completed",
        )
        db.add(version)
        db.flush()

        # Save chunks and their embeddings.
        for index, (chunk, vector, token_count) in enumerate(
            zip(chunks, vectors, token_counts)
        ):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    version_id=version.id,
                    chunk_index=index,
                    content=chunk,
                    token_count=token_count,
                    metadata_json={
                        "source_filename": safe_filename,
                        "chunk_index": index,
                        "char_count": len(chunk),
                    },
                    embedding=vector,
                )
            )

        document.current_version = version_number
        document.title = (title or safe_filename)[:500]
        document.content_type = content_type or "application/octet-stream"
        document.metadata_json = {
            "file_size_bytes": len(content),
            "sha256": checksum,
            "chunk_count": len(chunks),
        }
        document.status = "completed"
        db.commit()
        stored_path = None

        return {
            "document_id": str(document.id),
            "version_id": str(version.id),
            "filename": safe_filename,
            "status": document.status,
            "version_number": version_number,
            "chunk_count": len(chunks),
            "embedding_dimension": len(vectors[0]),
            "checksum": checksum,
            "duplicate": False,
        }

    except Exception:
        db.rollback()
        if stored_path is not None:
            try:
                remove_original(stored_path)
            except OSError:
                logger.warning("Could not remove an uncommitted document file")
        raise
