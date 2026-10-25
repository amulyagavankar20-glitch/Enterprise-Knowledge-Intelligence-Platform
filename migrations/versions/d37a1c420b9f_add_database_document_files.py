"""store original document bytes in PostgreSQL

Revision ID: d37a1c420b9f
Revises: ae8ca1c7f2fb
Create Date: 2026-10-25

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d37a1c420b9f"
down_revision: str | Sequence[str] | None = "ae8ca1c7f2fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_files",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("version_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_files = bind.execute(
        sa.text("SELECT 1 FROM document_files LIMIT 1")
    ).first()
    if has_files:
        raise RuntimeError(
            "Refusing to drop document_files while original uploads are stored there."
        )
    op.drop_table("document_files")
