"""create workflow runs

Revision ID: b7e142c6fa53
Revises: a6d031b5e942
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e142c6fa53"
down_revision: Union[str, Sequence[str], None] = "a6d031b5e942"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("current_task_id", sa.BigInteger(), nullable=True),
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("final_report", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("finalization_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name="check_workflow_run_status"),
        sa.ForeignKeyConstraint(["current_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency_key"),
    )
    op.create_index("ix_workflow_runs_plan_id", "workflow_runs", ["plan_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("ix_workflow_runs_lease_expires_at", "workflow_runs", ["lease_expires_at"])
    op.create_index("uq_workflow_runs_one_active_per_plan", "workflow_runs", ["plan_id"], unique=True, postgresql_where=sa.text("status IN ('pending', 'running')"))


def downgrade() -> None:
    op.drop_index("uq_workflow_runs_one_active_per_plan", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_lease_expires_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_plan_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
