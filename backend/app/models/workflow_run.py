from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent_handoff import AgentHandoff
    from app.models.plan import Plan
    from app.models.task import Task
    from app.models.task_execution import TaskExecution


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name="check_workflow_run_status"),
        Index("uq_workflow_runs_one_active_per_plan", "plan_id", unique=True, postgresql_where=text("status IN ('pending', 'running')")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    current_task_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    retried_from_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    finalization_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    finalizing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc))

    plan: Mapped["Plan"] = relationship("Plan", back_populates="workflow_runs")
    current_task: Mapped["Task | None"] = relationship("Task", foreign_keys=[current_task_id])
    task_executions: Mapped[list["TaskExecution"]] = relationship("TaskExecution", back_populates="workflow_run")
    handoffs: Mapped[list["AgentHandoff"]] = relationship("AgentHandoff", back_populates="workflow_run", cascade="all, delete-orphan")
    retried_from_run: Mapped["WorkflowRun | None"] = relationship("WorkflowRun", remote_side="WorkflowRun.id", back_populates="retry_runs", foreign_keys=[retried_from_run_id])
    retry_runs: Mapped[list["WorkflowRun"]] = relationship("WorkflowRun", back_populates="retried_from_run", foreign_keys=[retried_from_run_id])

    @property
    def current_task_title(self) -> str | None:
        return self.current_task.title if self.current_task else None

    @property
    def current_agent_id(self) -> str | None:
        return self.current_task.assigned_agent_id if self.current_task else None
