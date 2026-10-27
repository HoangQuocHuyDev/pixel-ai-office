from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ExecutionStatus = Literal["running", "completed", "failed", "cancelled"]


class TaskExecutionResponse(BaseModel):
    id: int
    task_id: int
    workflow_run_id: int | None = None
    agent_id: str
    status: ExecutionStatus
    input_snapshot: str
    output_content: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
