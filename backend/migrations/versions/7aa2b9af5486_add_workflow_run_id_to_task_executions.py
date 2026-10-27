"""add_workflow_run_id_to_task_executions

Revision ID: 7aa2b9af5486
Revises: f2b63d9a1e04
Create Date: 2026-10-27 08:47:43.268556

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7aa2b9af5486'
down_revision: Union[str, Sequence[str], None] = 'f2b63d9a1e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("task_executions", sa.Column("workflow_run_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_task_executions_workflow_run_id",
        "task_executions",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_task_executions_workflow_run_id", "task_executions", ["workflow_run_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_task_executions_workflow_run_id", table_name="task_executions")
    op.drop_constraint("fk_task_executions_workflow_run_id", "task_executions", type_="foreignkey")
    op.drop_column("task_executions", "workflow_run_id")
