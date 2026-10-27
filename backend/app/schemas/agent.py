from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.agents.models import AgentDefinition, AgentRole


class AgentPromptRequest(BaseModel):
    prompt: str
    conversation_id: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Prompt cannot be empty.")
        if len(trimmed) > 10000:
            raise ValueError("Prompt cannot exceed 10000 characters.")
        return trimmed

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Conversation ID must be a positive integer.")
        return value


class AgentPublicResponse(BaseModel):
    id: str
    name: str
    role: AgentRole
    description: str
    responsibilities: list[str]

    @classmethod
    def from_definition(cls, agent: AgentDefinition) -> "AgentPublicResponse":
        return cls(
            id=agent.id,
            name=agent.name,
            role=agent.role,
            description=agent.description,
            responsibilities=list(agent.responsibilities),
        )


class AgentActivityResponse(BaseModel):
    agent_id: str
    status: Literal["idle", "working", "failed"]
    current_task_id: int | None = None
    current_task_title: str | None = None
    workflow_run_id: int | None = None
    activity_type: str | None = None
    updated_at: datetime


class AgentExecutionStatistics(BaseModel):
    total_executions: int
    completed_executions: int
    failed_executions: int
    cancelled_executions: int
    success_rate: float | None
    average_duration_seconds: float | None
    last_active_at: datetime | None


class AgentExecutionResponse(BaseModel):
    id: int
    task_id: int
    task_title: str
    workflow_run_id: int | None = None
    status: Literal["running", "completed", "failed", "cancelled"]
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    output_content: str | None
    error_code: str | None
    error_message: str | None


class AgentTaskReference(BaseModel):
    id: int
    title: str
    status: str


class AgentWorkflowReference(BaseModel):
    id: int
    plan_id: int
    plan_title: str
    status: str


class AgentMonitoringResponse(BaseModel):
    agent: AgentPublicResponse
    current_activity: AgentActivityResponse
    current_task: AgentTaskReference | None
    current_workflow: AgentWorkflowReference | None
    statistics: AgentExecutionStatistics
    recent_executions: list[AgentExecutionResponse]


class AgentTimelineEvent(BaseModel):
    event_id: str
    event_type: str
    agent_id: str
    task_id: int | None = None
    workflow_run_id: int | None = None
    execution_id: int | None = None
    status: str
    timestamp: datetime
    description: str


class AgentTimelineResponse(BaseModel):
    items: list[AgentTimelineEvent]
    total: int
    limit: int
    offset: int


class AgentMonitoringSummary(BaseModel):
    total_agents: int
    working_agents: int
    idle_agents: int
    failed_agents: int
    total_executions: int
    completed_executions: int
    failed_executions: int
    active_workflows: int
