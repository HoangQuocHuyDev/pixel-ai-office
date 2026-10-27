"""create artifacts

Revision ID: e9a41c2d7f30
Revises: c8f253d70b64
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9a41c2d7f30"
down_revision: str | None = "c8f253d70b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("artifact_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(30), nullable=False),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("agent_id", sa.String(50), nullable=True),
        sa.Column("task_id", sa.BigInteger(), nullable=True),
        sa.Column("task_execution_id", sa.BigInteger(), nullable=True),
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("artifact_type IN ('document', 'code', 'research', 'report')", name="check_artifact_type"),
        sa.CheckConstraint("content_format IN ('plain_text', 'markdown', 'json', 'code')", name="check_artifact_content_format"),
        sa.CheckConstraint("char_length(content) BETWEEN 1 AND 1000000", name="check_artifact_content_size"),
        sa.CheckConstraint("task_execution_id IS NOT NULL OR workflow_run_id IS NOT NULL", name="check_artifact_has_source"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_execution_id"], ["task_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_execution_id", name="uq_artifacts_task_execution_id"),
        sa.UniqueConstraint("workflow_run_id", name="uq_artifacts_workflow_run_id"),
    )
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])
    op.create_index("ix_artifacts_agent_id", "artifacts", ["agent_id"])
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_task_id", table_name="artifacts")
    op.drop_index("ix_artifacts_agent_id", table_name="artifacts")
    op.drop_index("ix_artifacts_artifact_type", table_name="artifacts")
    op.drop_table("artifacts")
