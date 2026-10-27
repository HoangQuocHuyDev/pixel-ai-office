"""create plans and link tasks

Revision ID: f5c920a4d831
Revises: d4b819e3a712
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5c920a4d831"
down_revision: Union[str, Sequence[str], None] = "d4b819e3a712"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default="approved", nullable=False),
        sa.Column("source_conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'approved', 'cancelled')", name="check_plan_status"),
        sa.ForeignKeyConstraint(["source_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_plans_idempotency_key"),
    )
    op.create_index("ix_plans_status", "plans", ["status"])
    op.create_index("ix_plans_source_conversation_id", "plans", ["source_conversation_id"])
    op.add_column("tasks", sa.Column("plan_id", sa.BigInteger(), nullable=True))
    op.add_column("tasks", sa.Column("sequence_order", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_tasks_plan_id", "tasks", "plans", ["plan_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("check_task_sequence_order", "tasks", "sequence_order IS NULL OR sequence_order > 0")
    op.create_unique_constraint("uq_tasks_plan_sequence_order", "tasks", ["plan_id", "sequence_order"])
    op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_plan_id", table_name="tasks")
    op.drop_constraint("uq_tasks_plan_sequence_order", "tasks", type_="unique")
    op.drop_constraint("check_task_sequence_order", "tasks", type_="check")
    op.drop_constraint("fk_tasks_plan_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "sequence_order")
    op.drop_column("tasks", "plan_id")
    op.drop_index("ix_plans_source_conversation_id", table_name="plans")
    op.drop_index("ix_plans_status", table_name="plans")
    op.drop_table("plans")
