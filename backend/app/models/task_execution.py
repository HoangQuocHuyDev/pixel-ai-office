from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.workflow_run import WorkflowRun


class TaskExecution(Base):
    __tablename__ = "task_executions"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled')", name="check_task_execution_status"),
        Index("uq_task_executions_one_running_per_task", "task_id", unique=True, postgresql_where=text("status = 'running'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    execution_lease_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    input_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    output_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="executions")
    workflow_run: Mapped["WorkflowRun | None"] = relationship("WorkflowRun", back_populates="task_executions")
