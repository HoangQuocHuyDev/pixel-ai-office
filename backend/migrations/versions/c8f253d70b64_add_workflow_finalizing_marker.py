"""add workflow finalizing marker

Revision ID: c8f253d70b64
Revises: b7e142c6fa53
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8f253d70b64"
down_revision: Union[str, Sequence[str], None] = "b7e142c6fa53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("finalizing_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_runs", "finalizing_at")
