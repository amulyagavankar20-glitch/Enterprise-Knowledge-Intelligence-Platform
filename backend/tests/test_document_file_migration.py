import hashlib
from types import SimpleNamespace
from uuid import uuid4

from app.db.models import DocumentFile, DocumentVersion

from scripts.migrate_document_files import migrate_legacy_files


class MigrationDB:
    def __init__(self, versions, *, fail_commit=False):
        self.versions = versions
        self.files = {}
        self.pending = []
        self.fail_commit = fail_commit
        self.rolled_back = False

    def query(self, model):
        assert model is DocumentVersion
        return SimpleNamespace(all=lambda: self.versions)

    def get(self, model, version_id):
        assert model is DocumentFile
        return self.files.get(version_id)

    def add(self, row):
        self.pending.append(row)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("simulated database failure")
        self.files.update({row.version_id: row for row in self.pending})
        self.pending.clear()

    def rollback(self):
        self.pending.clear()
        self.rolled_back = True

    def refresh(self, row):
        assert self.files.get(row.version_id) is row


def legacy_version(content, storage_path="doc/1/original.txt"):
    return SimpleNamespace(
        id=uuid4(),
        checksum=hashlib.sha256(content).hexdigest(),
        storage_path=storage_path,
    )


def test_migration_copies_and_verifies_bytes_without_deleting_legacy_file(tmp_path):
    content = b"original bytes"
    version = legacy_version(content)
    original = tmp_path / version.storage_path
    original.parent.mkdir(parents=True)
    original.write_bytes(content)
    db = MigrationDB([version])

    report = migrate_legacy_files(db, root=tmp_path)

    assert report["migrated"] == 1
    assert report["checksum_mismatch"] == report["missing"] == report["failed"] == 0
    assert db.files[version.id].content == content
    assert original.read_bytes() == content
    assert migrate_legacy_files(db, root=tmp_path, verify_only=True)["already_valid"] == 1


def test_migration_checksum_mismatch_keeps_local_file_and_does_not_import(tmp_path):
    version = legacy_version(b"expected")
    original = tmp_path / version.storage_path
    original.parent.mkdir(parents=True)
    original.write_bytes(b"different bytes")
    db = MigrationDB([version])

    report = migrate_legacy_files(db, root=tmp_path)

    assert report["checksum_mismatch"] == 1
    assert not db.files
    assert original.read_bytes() == b"different bytes"


def test_migration_database_failure_rolls_back_and_keeps_local_file(tmp_path):
    content = b"preserved source file"
    version = legacy_version(content)
    original = tmp_path / version.storage_path
    original.parent.mkdir(parents=True)
    original.write_bytes(content)
    db = MigrationDB([version], fail_commit=True)

    report = migrate_legacy_files(db, root=tmp_path)

    assert report["failed"] == 1
    assert db.rolled_back
    assert not db.files
    assert original.read_bytes() == content
