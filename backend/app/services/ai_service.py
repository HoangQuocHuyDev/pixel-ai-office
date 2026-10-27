from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

from app.ai.base import BaseAIProvider
from app.ai.factory import get_ai_provider
from app.core.exceptions import ApplicationError
from app.schemas.ai import AIPromptRequest, AIResponse

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class AIService:
    def __init__(self, provider: BaseAIProvider | None = None) -> None:
        self._provider = provider

    def _get_provider(self) -> BaseAIProvider:
        if self._provider is None:
            self._provider = get_ai_provider()
        return self._provider

    def ensure_ready(self) -> None:
        """Initialize and validate the configured provider before a stream starts."""
        self._get_provider()

    async def generate_response(
        self,
        request: AIPromptRequest,
    ) -> AIResponse:
        trimmed_prompt = request.prompt.strip()
        if not trimmed_prompt:
            raise ApplicationError(
                status_code=422,
                error_code="VALIDATION_ERROR",
                message="Prompt cannot be empty.",
            )

        provider = self._get_provider()
        return await provider.generate(
            prompt=trimmed_prompt,
            system_instruction=request.system_instruction,
        )

    async def generate_response_stream(
        self,
        request: AIPromptRequest,
    ) -> AsyncIterator[str]:
        trimmed_prompt = request.prompt.strip()
        if not trimmed_prompt:
            raise ApplicationError(
                status_code=422,
                error_code="VALIDATION_ERROR",
                message="Prompt cannot be empty.",
            )

        provider = self._get_provider()
        async for chunk in provider.generate_stream(
            prompt=trimmed_prompt,
            system_instruction=request.system_instruction,
        ):
            yield chunk

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[StructuredModel],
        system_instruction: str | None = None,
    ) -> StructuredModel:
        trimmed_prompt = prompt.strip()
        if not trimmed_prompt:
            raise ApplicationError(422, "VALIDATION_ERROR", "Prompt cannot be empty.")
        return await self._get_provider().generate_structured(
            trimmed_prompt,
            response_schema,
            system_instruction,
        )
