from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("artifact_type IN ('document', 'code', 'research', 'report')", name="check_artifact_type"),
        CheckConstraint("content_format IN ('plain_text', 'markdown', 'json', 'code')", name="check_artifact_content_format"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 1000000", name="check_artifact_content_size"),
        CheckConstraint("task_execution_id IS NOT NULL OR workflow_run_id IS NOT NULL", name="check_artifact_has_source"),
        CheckConstraint("current_version_number >= 1", name="check_artifact_current_version"),
        UniqueConstraint("task_execution_id", name="uq_artifacts_task_execution_id"),
        UniqueConstraint("workflow_run_id", name="uq_artifacts_workflow_run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    task_execution_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("task_executions.id", ondelete="CASCADE"), nullable=True)
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True)
    current_version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc))
