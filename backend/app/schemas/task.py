from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

TaskStatus = Literal["todo", "in_progress", "done", "cancelled"]
TaskPriority = Literal["low", "medium", "high"]


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    assigned_agent_id: str | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def title_valid(cls, value: str) -> str:
        value = value.strip()
        if not value: raise ValueError("Task title cannot be empty.")
        if len(value) > 200: raise ValueError("Task title cannot exceed 200 characters.")
        return value

    @field_validator("description")
    @classmethod
    def description_valid(cls, value: str | None) -> str | None:
        if value is None: return None
        value = value.strip()
        if len(value) > 5000: raise ValueError("Task description cannot exceed 5000 characters.")
        return value or None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assigned_agent_id: str | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def title_valid(cls, value: str | None) -> str | None:
        if value is None: raise ValueError("Task title cannot be null.")
        value = value.strip()
        if not value: raise ValueError("Task title cannot be empty.")
        if len(value) > 200: raise ValueError("Task title cannot exceed 200 characters.")
        return value

    @field_validator("description")
    @classmethod
    def description_valid(cls, value: str | None) -> str | None:
        if value is None: return None
        value = value.strip()
        if len(value) > 5000: raise ValueError("Task description cannot exceed 5000 characters.")
        return value or None

    @field_validator("status", "priority")
    @classmethod
    def enum_not_null(cls, value: str | None) -> str:
        if value is None: raise ValueError("Status and priority cannot be null.")
        return value


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    model_config = ConfigDict(extra="forbid")


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assigned_agent_id: str | None
    plan_id: int | None
    sequence_order: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
