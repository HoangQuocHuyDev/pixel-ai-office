from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.task_execution import TaskExecution
    from app.models.workflow_run import WorkflowRun


class AgentHandoff(Base):
    __tablename__ = "agent_handoffs"
    __table_args__ = (
        UniqueConstraint("source_task_execution_id", "target_task_id", name="uq_agent_handoffs_source_target"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_task_execution_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("task_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    target_task_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    target_agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_findings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    deliverables: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())

    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="handoffs")
    source_execution: Mapped["TaskExecution"] = relationship("TaskExecution")
    target_task: Mapped["Task"] = relationship("Task")

