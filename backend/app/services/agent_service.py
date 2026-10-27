from collections.abc import AsyncIterator

from app.agents.registry import AgentRegistry, default_agent_registry
from app.schemas.ai import AIPromptRequest, AIResponse
from app.services.ai_service import AIService


class AgentService:
    def __init__(
        self,
        ai_service: AIService | None = None,
        registry: AgentRegistry = default_agent_registry,
    ) -> None:
        self._ai_service = ai_service or AIService()
        self._registry = registry

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        request = self._create_request(agent_id, prompt)
        return await self._ai_service.generate_response(request)

    async def generate_response_stream(
        self,
        agent_id: str,
        prompt: str,
    ) -> AsyncIterator[str]:
        request = self._create_request(agent_id, prompt)
        async for chunk in self._ai_service.generate_response_stream(request):
            yield chunk

    def ensure_ready(self) -> None:
        self._ai_service.ensure_ready()

    def _create_request(self, agent_id: str, prompt: str) -> AIPromptRequest:
        agent = self._registry.get(agent_id)
        return AIPromptRequest(
            prompt=prompt,
            system_instruction=agent.system_instruction,
        )
