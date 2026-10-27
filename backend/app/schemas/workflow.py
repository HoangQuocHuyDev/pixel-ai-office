from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class WorkflowStartRequest(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    model_config = ConfigDict(extra="forbid")


class WorkflowRetryRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    model_config = ConfigDict(extra="forbid")


class WorkflowRunResponse(BaseModel):
    id: int
    plan_id: int
    status: WorkflowStatus
    current_task_id: int | None
    current_task_title: str | None = None
    current_agent_id: str | None = None
    completed_tasks: int
    total_tasks: int
    final_report: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime
    can_retry: bool = False
    retry_block_reason: str | None = None
    retried_from_run_id: int | None = None
    retry_run_ids: list[int] = []
    failed_task_title: str | None = None
    failed_task_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class WorkflowArtifactReference(BaseModel):
    id: int
    title: str
    artifact_type: str
    agent_id: str | None
    task_execution_id: int | None
    workflow_run_id: int | None
    created_at: datetime


class WorkflowExecutionAttempt(BaseModel):
    id: int
    attempt_number: int
    status: Literal["running", "completed", "failed", "cancelled"]
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    result_preview: str | None
    result_truncated: bool
    error_code: str | None
    error_message: str | None
    artifacts: list[WorkflowArtifactReference]


class WorkflowTimelineStep(BaseModel):
    step_number: int
    task_id: int
    task_title: str
    task_description: str | None
    agent_id: str | None
    agent_name: str | None
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    attempts: list[WorkflowExecutionAttempt]
    pre_existing: bool = False
    reused_from_run_id: int | None = None
    reused_execution_id: int | None = None


class WorkflowProgressSummary(BaseModel):
    total_tasks: int
    completed_tasks: int
    running_tasks: int
    pending_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    progress_percentage: float


class WorkflowHandoffResponse(BaseModel):
    id: int
    workflow_run_id: int
    source_task_execution_id: int
    source_task_id: int
    source_task_title: str
    source_agent_id: str
    source_agent_name: str | None = None
    target_task_id: int
    target_task_title: str
    target_agent_id: str
    target_agent_name: str | None = None
    summary: str
    key_findings: list[str] = []
    deliverables: list[str] = []
    next_steps: str | None = None
    artifacts: list[WorkflowArtifactReference] = []
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorkflowFinalization(BaseModel):
    status: Literal["not_started", "pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime | None
    completed_at: datetime | None
    report_preview: str | None
    report_truncated: bool
    error_code: str | None
    error_message: str | None
    artifacts: list[WorkflowArtifactReference]


class WorkflowPlanMetadata(BaseModel):
    id: int
    title: str
    objective: str
    status: str
    created_at: datetime
    approval_timestamp_available: bool = False


class WorkflowTimelineResponse(BaseModel):
    workflow_id: int
    status: WorkflowStatus
    plan: WorkflowPlanMetadata
    started_at: datetime
    completed_at: datetime | None
    updated_at: datetime
    progress: WorkflowProgressSummary
    steps: list[WorkflowTimelineStep]
    handoffs: list[WorkflowHandoffResponse] = []
    finalization: WorkflowFinalization
    error_code: str | None
    error_message: str | None
    execution_scope_note: str
    can_retry: bool = False
    retry_block_reason: str | None = None
    retried_from_run_id: int | None = None
    retry_run_ids: list[int] = []
    failed_task_title: str | None = None
    failed_task_id: int | None = None
