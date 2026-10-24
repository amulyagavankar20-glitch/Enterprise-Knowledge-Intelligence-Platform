"""Safe filesystem persistence for uploaded original documents."""

import os
import shutil
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def storage_root() -> Path:
    configured = os.getenv("DOCUMENT_STORAGE_DIR")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            root = PROJECT_ROOT / root
    else:
        root = PROJECT_ROOT / "stored_documents"
    return root.resolve()


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def persist_original(
    *, document_id: uuid.UUID,
    version_number: int,
    filename: str,
    content: bytes,
) -> str:
    root = storage_root()
    relative_path = Path(str(document_id)) / str(version_number) / Path(filename).name
    target = (root / relative_path).resolve()
    if not _within_root(target, root):
        raise ValueError("Invalid document storage path.")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return relative_path.as_posix()


def resolve_original(storage_path: str) -> Path | None:
    root = storage_root()
    relative = Path(storage_path)
    if relative.is_absolute():
        return None
    target = (root / relative).resolve()
    if not _within_root(target, root) or not target.is_file():
        return None
    return target


def remove_original(storage_path: str) -> None:
    target = resolve_original(storage_path)
    if target is not None:
        target.unlink(missing_ok=True)


def remove_document_files(document_id: uuid.UUID) -> None:
    root = storage_root()
    document_dir = (root / str(document_id)).resolve()
    if _within_root(document_dir, root) and document_dir.is_dir():
        shutil.rmtree(document_dir)
