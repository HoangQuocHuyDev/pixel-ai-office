from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.workflow_run import WorkflowRun


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (CheckConstraint("status IN ('draft', 'approved', 'cancelled')", name="check_plan_status"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved", server_default="approved", index=True)
    source_conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="plan", order_by="Task.sequence_order.asc()")
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship("WorkflowRun", back_populates="plan", cascade="all, delete-orphan")
