from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.task_execution import TaskExecution


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo', 'in_progress', 'done', 'cancelled')", name="check_task_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="check_task_priority"),
        CheckConstraint("sequence_order IS NULL OR sequence_order > 0", name="check_task_sequence_order"),
        UniqueConstraint("plan_id", "sequence_order", name="uq_tasks_plan_sequence_order"),
        Index("ix_tasks_created_at_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo", server_default="todo", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default="medium")
    assigned_agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    sequence_order: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan: Mapped["Plan | None"] = relationship("Plan", back_populates="tasks")
    executions: Mapped[list["TaskExecution"]] = relationship("TaskExecution", back_populates="task", cascade="all, delete-orphan")
