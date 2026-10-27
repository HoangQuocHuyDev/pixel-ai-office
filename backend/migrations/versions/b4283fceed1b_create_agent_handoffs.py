"""create_agent_handoffs

Revision ID: b4283fceed1b
Revises: 7aa2b9af5486
Create Date: 2026-10-27 09:32:00.333851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4283fceed1b'
down_revision: Union[str, Sequence[str], None] = '7aa2b9af5486'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_handoffs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=False),
        sa.Column("source_task_execution_id", sa.BigInteger(), nullable=False),
        sa.Column("source_agent_id", sa.String(50), nullable=False),
        sa.Column("target_task_id", sa.BigInteger(), nullable=False),
        sa.Column("target_agent_id", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_findings", sa.JSON(), nullable=False),
        sa.Column("deliverables", sa.JSON(), nullable=False),
        sa.Column("next_steps", sa.Text(), nullable=True),
        sa.Column("artifact_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_task_execution_id"], ["task_executions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_task_execution_id", "target_task_id", name="uq_agent_handoffs_source_target"),
    )
    op.create_index("ix_agent_handoffs_workflow_run_id", "agent_handoffs", ["workflow_run_id"])
    op.create_index("ix_agent_handoffs_source_task_execution_id", "agent_handoffs", ["source_task_execution_id"])
    op.create_index("ix_agent_handoffs_target_task_id", "agent_handoffs", ["target_task_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_agent_handoffs_target_task_id", table_name="agent_handoffs")
    op.drop_index("ix_agent_handoffs_source_task_execution_id", table_name="agent_handoffs")
    op.drop_index("ix_agent_handoffs_workflow_run_id", table_name="agent_handoffs")
    op.drop_table("agent_handoffs")
