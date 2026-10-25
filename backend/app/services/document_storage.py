"""Legacy filesystem path resolution for the one-time PostgreSQL importer.

Application uploads and downloads use PostgreSQL. This helper exists only so
the migration utility can safely read old files without deleting them.
"""

import os
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


def resolve_legacy_file(storage_path: str, root: Path | None = None) -> Path | None:
    """Resolve a legacy path only when it remains within the configured root."""
    root = (root or storage_root()).resolve()
    relative = Path(storage_path)
    if relative.is_absolute():
        return None
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target if target.is_file() else None
