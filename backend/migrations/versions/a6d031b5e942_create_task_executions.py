"""create task executions

Revision ID: a6d031b5e942
Revises: f5c920a4d831
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a6d031b5e942"
down_revision: Union[str, Sequence[str], None] = "f5c920a4d831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_executions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_snapshot", sa.Text(), nullable=False),
        sa.Column("output_content", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled')", name="check_task_execution_status"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_executions_task_id", "task_executions", ["task_id"])
    op.create_index("ix_task_executions_status", "task_executions", ["status"])
    op.create_index(
        "uq_task_executions_one_running_per_task",
        "task_executions",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_task_executions_one_running_per_task", table_name="task_executions")
    op.drop_index("ix_task_executions_status", table_name="task_executions")
    op.drop_index("ix_task_executions_task_id", table_name="task_executions")
    op.drop_table("task_executions")
