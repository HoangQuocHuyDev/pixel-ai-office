"""add artifact versions

Revision ID: f2b63d9a1e04
Revises: e9a41c2d7f30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b63d9a1e04"
down_revision: str | None = "e9a41c2d7f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("current_version_number", sa.Integer(), server_default="1", nullable=False))
    op.create_check_constraint("check_artifact_current_version", "artifacts", "current_version_number >= 1")
    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("artifact_id", sa.BigInteger(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(30), nullable=False),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("change_summary", sa.String(500), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("restored_from_version_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="check_artifact_version_number"),
        sa.CheckConstraint("source IN ('agent', 'user', 'restore', 'backfill')", name="check_artifact_version_source"),
        sa.CheckConstraint("content_format IN ('plain_text', 'markdown', 'json', 'code')", name="check_artifact_version_format"),
        sa.CheckConstraint("char_length(content) BETWEEN 1 AND 1000000", name="check_artifact_version_content_size"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "version_number", name="uq_artifact_versions_number"),
        sa.UniqueConstraint("artifact_id", "id", name="uq_artifact_versions_artifact_id_id"),
    )
    op.create_index("ix_artifact_versions_artifact_id", "artifact_versions", ["artifact_id"])
    op.execute(sa.text("""
        INSERT INTO artifact_versions (artifact_id, version_number, content, content_format, language, source, change_summary)
        SELECT id, 1, content, content_format, language, 'backfill', 'Original version backfilled from the existing artifact.'
        FROM artifacts
        ON CONFLICT (artifact_id, version_number) DO NOTHING
    """))
    op.create_foreign_key(
        "fk_artifact_version_restore_same_artifact", "artifact_versions", "artifact_versions",
        ["artifact_id", "restored_from_version_id"], ["artifact_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_artifact_version_restore_same_artifact", "artifact_versions", type_="foreignkey")
    op.drop_index("ix_artifact_versions_artifact_id", table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_constraint("check_artifact_current_version", "artifacts", type_="check")
    op.drop_column("artifacts", "current_version_number")
