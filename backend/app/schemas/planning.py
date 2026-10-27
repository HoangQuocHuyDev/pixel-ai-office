from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.task import TaskResponse

DelegateAgentId = Literal["developer", "researcher"]


class PlannedTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    priority: Literal["low", "medium", "high"]
    assigned_agent_id: DelegateAgentId
    sequence_order: int = Field(ge=1, le=10)
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Planning text cannot be empty.")
        return value


class PlanProposal(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=5000)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=10)
    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "objective")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Plan text cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_sequence(self) -> "PlanProposal":
        sequence = sorted(task.sequence_order for task in self.tasks)
        if sequence != list(range(1, len(self.tasks) + 1)):
            raise ValueError("Task sequence_order values must be unique and contiguous from 1.")
        return self


class PlanGenerateRequest(BaseModel):
    objective: str = Field(min_length=10, max_length=5000)
    source_conversation_id: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(extra="forbid")

    @field_validator("objective")
    @classmethod
    def trim_objective(cls, value: str) -> str:
        return value.strip()


class PlanApproveRequest(BaseModel):
    proposal: PlanProposal
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    source_conversation_id: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(extra="forbid")


class PlanSummary(BaseModel):
    id: int
    title: str
    objective: str
    status: Literal["draft", "approved", "cancelled"]
    source_conversation_id: int | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PlanResponse(PlanSummary):
    tasks: list[TaskResponse]
