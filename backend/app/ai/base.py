from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

from app.schemas.ai import AIResponse

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class BaseAIProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the AI provider (e.g. 'gemini')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the active model."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> AIResponse:
        """Asynchronously generates text content for the given prompt."""
        pass

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> AsyncIterator[str]:
        """Asynchronously streams text chunks for the given prompt."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[StructuredModel],
        system_instruction: str | None = None,
    ) -> StructuredModel:
        """Generate provider-native structured output validated by a Pydantic schema."""
        pass
