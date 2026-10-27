from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class AIPromptRequest(BaseModel):
    prompt: str
    system_instruction: str | None = None
    conversation_id: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Conversation ID must be a positive integer.")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Prompt cannot be empty.")
        if len(trimmed) > 10000:
            raise ValueError("Prompt cannot exceed 10000 characters.")
        return trimmed

    @field_validator("system_instruction")
    @classmethod
    def validate_system_instruction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 4000:
            raise ValueError("System instruction cannot exceed 4000 characters.")
        return trimmed


class AIResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage_metadata: dict[str, Any] | None = None
    finish_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)
