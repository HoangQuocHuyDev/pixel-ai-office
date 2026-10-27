"""create_tasks_table

Revision ID: d4b819e3a712
Revises: 8c41a6b27e90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4b819e3a712"
down_revision: Union[str, Sequence[str], None] = "8c41a6b27e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="todo", nullable=False),
        sa.Column("priority", sa.String(20), server_default="medium", nullable=False),
        sa.Column("assigned_agent_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('todo', 'in_progress', 'done', 'cancelled')", name="check_task_status"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name="check_task_priority"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_assigned_agent_id", "tasks", ["assigned_agent_id"])
    op.create_index("ix_tasks_created_at_id", "tasks", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_created_at_id", table_name="tasks")
    op.drop_index("ix_tasks_assigned_agent_id", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")
