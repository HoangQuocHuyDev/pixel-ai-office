import re
from collections.abc import Iterable

from app.agents.definitions import DEFAULT_AGENTS
from app.agents.models import AgentDefinition
from app.core.exceptions import ApplicationError


AGENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,49}$")


class AgentRegistry:
    def __init__(self, agents: Iterable[AgentDefinition]) -> None:
        registered: dict[str, AgentDefinition] = {}
        for agent in agents:
            self.validate_id(agent.id)
            if agent.id in registered:
                raise ValueError(f"Duplicate agent ID: {agent.id}")
            registered[agent.id] = agent
        self._agents = registered

    @staticmethod
    def validate_id(agent_id: str) -> str:
        normalized = agent_id.strip()
        if not AGENT_ID_PATTERN.fullmatch(normalized):
            raise ApplicationError(
                status_code=400,
                error_code="INVALID_AGENT_ID",
                message="Agent ID has an invalid format.",
            )
        return normalized

    def get(self, agent_id: str) -> AgentDefinition:
        normalized = self.validate_id(agent_id)
        agent = self._agents.get(normalized)
        if agent is None:
            raise ApplicationError(
                status_code=404,
                error_code="AGENT_NOT_FOUND",
                message=f"Agent '{normalized}' was not found.",
            )
        return agent

    def list(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._agents.values())


default_agent_registry = AgentRegistry(DEFAULT_AGENTS)
