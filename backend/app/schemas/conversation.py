from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.message import MessageResponse
from app.agents.registry import default_agent_registry
from app.core.exceptions import ApplicationError


class ConversationCreate(BaseModel):
    title: str
    agent_id: str = "manager"

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Conversation title cannot be empty.")
        if len(trimmed) > 150:
            raise ValueError("Conversation title cannot exceed 150 characters.")
        return trimmed

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, value: str) -> str:
        try:
            return default_agent_registry.get(value).id
        except ApplicationError as exc:
            raise ValueError(exc.message) from exc


class ConversationResponse(BaseModel):
    id: int
    title: str
    agent_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = []

    model_config = ConfigDict(from_attributes=True)

