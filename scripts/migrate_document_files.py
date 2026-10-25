"""Copy legacy stored_documents originals into PostgreSQL and verify hashes.

This utility never deletes or modifies local files. Run it after applying the
document_files Alembic migration, then run it again with --verify-only.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.db.database import SessionLocal
from app.db.models import DocumentFile, DocumentVersion
from app.services.document_storage import resolve_legacy_file, storage_root

DATABASE_MARKER = "database://"


def migrate_legacy_files(
    db: Any,
    *,
    root: Path | None = None,
    verify_only: bool = False,
) -> dict[str, int]:
    """Import eligible legacy files and verify every stored blob by SHA-256."""
    report = {
        "versions_checked": 0,
        "migrated": 0,
        "already_valid": 0,
        "missing": 0,
        "checksum_mismatch": 0,
        "failed": 0,
    }
    root = root or storage_root()

    for version in db.query(DocumentVersion).all():
        report["versions_checked"] += 1
        stored = db.get(DocumentFile, version.id)
        if stored is not None:
            if hashlib.sha256(stored.content).hexdigest() == version.checksum:
                report["already_valid"] += 1
            else:
                report["checksum_mismatch"] += 1
            continue

        if verify_only or version.storage_path.startswith(DATABASE_MARKER):
            report["missing"] += 1
            continue

        legacy_file = resolve_legacy_file(version.storage_path, root)
        if legacy_file is None:
            report["missing"] += 1
            continue

        try:
            content = legacy_file.read_bytes()
            if hashlib.sha256(content).hexdigest() != version.checksum:
                report["checksum_mismatch"] += 1
                continue

            db.add(DocumentFile(version_id=version.id, content=content))
            db.commit()
            stored = db.get(DocumentFile, version.id)
            if stored is not None:
                db.refresh(stored)
            if stored is None or hashlib.sha256(stored.content).hexdigest() != version.checksum:
                report["failed"] += 1
                continue
            report["migrated"] += 1
        except Exception:  # noqa: BLE001 - report per-file failures without stopping later imports.
            db.rollback()
            report["failed"] += 1

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        help="Legacy storage root (defaults to stored_documents or DOCUMENT_STORAGE_DIR).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify that every version has a PostgreSQL blob matching its checksum.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = migrate_legacy_files(db, root=args.root, verify_only=args.verify_only)
    finally:
        db.close()

    print(json.dumps(report, indent=2, sort_keys=True))
    return int(any(report[key] for key in ("missing", "checksum_mismatch", "failed")))


if __name__ == "__main__":
    raise SystemExit(main())
