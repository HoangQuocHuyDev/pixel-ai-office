"""add_agent_id_to_conversations

Revision ID: 8c41a6b27e90
Revises: 19ec952fd6e9
Create Date: 2026-10-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c41a6b27e90"
down_revision: Union[str, Sequence[str], None] = "19ec952fd6e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "agent_id",
            sa.String(length=50),
            nullable=True,
            server_default=sa.text("'manager'"),
        ),
    )
    op.execute("UPDATE conversations SET agent_id = 'manager' WHERE agent_id IS NULL")
    op.alter_column("conversations", "agent_id", nullable=False)
    op.create_check_constraint(
        "check_conversation_agent_id",
        "conversations",
        "agent_id IN ('manager', 'developer', 'researcher')",
    )
    op.create_index("ix_conversations_agent_id", "conversations", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_agent_id", table_name="conversations")
    op.drop_constraint(
        "check_conversation_agent_id",
        "conversations",
        type_="check",
    )
    op.drop_column("conversations", "agent_id")
