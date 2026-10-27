from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class MessageCreate(BaseModel):
    content: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Message content cannot be empty.")
        if len(trimmed) > 4000:
            raise ValueError("Message content cannot exceed 4000 characters.")
        return trimmed


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

