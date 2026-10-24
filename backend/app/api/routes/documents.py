import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.dependencies import get_db
from app.db.models import Document, DocumentChunk, DocumentVersion, User
from app.services.auth import get_current_user
from app.services.audit import record_audit
from app.services.document_storage import remove_document_files, resolve_original
from app.services.ingestion import ingest_document
from app.services.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _document_query(db: Session, user: User):
    query = db.query(Document)
    if user.role != "admin":
        query = query.filter(Document.owner_id == user.id)
    return query


def _get_document(db: Session, user: User, document_id: uuid.UUID) -> Document:
    document = _document_query(db, user).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.post("/upload", status_code=201)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    title: Annotated[str | None, Form(max_length=500)] = None,
):
    enforce_rate_limit(request, scope="upload", limit=10)
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(
            status_code=415,
            detail="Supported formats: PDF, DOCX, TXT, Markdown.",
        )

    try:
        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds 20 MB.")
        result = ingest_document(
            db,
            owner_id=user.id,
            filename=filename,
            content=content,
            title=title,
            content_type=file.content_type,
        )
        record_audit(
            db,
            actor_id=user.id,
            action=("document.duplicate_upload" if result.get("duplicate") else "document.uploaded"),
            resource_type="document",
            resource_id=result.get("document_id"),
            details={
                "version_number": result.get("version_number"),
                "chunk_count": result.get("chunk_count"),
            },
        )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Document ingestion failed.",
        ) from exc
    finally:
        await file.close()


@router.get("")
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    documents = (
        _document_query(db, user)
        .filter(Document.status == "completed")
        .order_by(Document.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": str(document.id),
                "title": document.title,
                "filename": document.filename,
                "content_type": document.content_type,
                "current_version": document.current_version,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
            }
            for document in documents
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{document_id}")
def get_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = _get_document(db, user, document_id)
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version,
        )
        .first()
    )
    chunk_count = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.version_id == version.id)
        .count()
        if version else 0
    )
    return {
        "id": str(document.id),
        "title": document.title,
        "filename": document.filename,
        "content_type": document.content_type,
        "current_version": document.current_version,
        "chunk_count": chunk_count,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


@router.get("/{document_id}/content")
def get_document_content(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    version_number: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    document = _get_document(db, user, document_id)
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == (
                version_number or document.current_version
            ),
        )
        .first()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Document version not found.")
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.version_id == version.id)
        .order_by(DocumentChunk.chunk_index)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "document_id": str(document.id),
        "version_number": version.version_number,
        "items": [
            {
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "content": chunk.content,
            }
            for chunk in chunks
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{document_id}/versions")
def list_document_versions(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = _get_document(db, user, document_id)
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )
    return {
        "document_id": str(document.id),
        "items": [
            {
                "version_number": version.version_number,
                "checksum": version.checksum,
                "status": version.status,
                "created_at": version.created_at,
                "original_available": resolve_original(version.storage_path) is not None,
            }
            for version in versions
        ],
    }


@router.get("/{document_id}/file")
def download_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = _get_document(db, user, document_id)
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == document.current_version,
        )
        .first()
    )
    path = resolve_original(version.storage_path) if version else None
    if path is None:
        raise HTTPException(status_code=404, detail="Original file is unavailable.")
    record_audit(
        db,
        actor_id=user.id,
        action="document.downloaded",
        resource_type="document",
        resource_id=str(document.id),
        details={"version_number": document.current_version},
    )
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.filename,
    )


@router.get("/{document_id}/versions/{version_number}/file")
def download_document_version(
    document_id: uuid.UUID,
    version_number: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = _get_document(db, user, document_id)
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_number == version_number,
        )
        .first()
    )
    path = resolve_original(version.storage_path) if version else None
    if path is None:
        raise HTTPException(status_code=404, detail="Original file is unavailable.")
    record_audit(
        db,
        actor_id=user.id,
        action="document.version_downloaded",
        resource_type="document",
        resource_id=str(document.id),
        details={"version_number": version_number},
    )
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.filename,
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    document = _get_document(db, user, document_id)
    db.delete(document)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Document deletion failed.",
        ) from exc
    try:
        remove_document_files(document_id)
    except OSError:
        logger.warning("Could not remove stored files for deleted document")
    record_audit(
        db,
        actor_id=user.id,
        action="document.deleted",
        resource_type="document",
        resource_id=str(document_id),
    )
