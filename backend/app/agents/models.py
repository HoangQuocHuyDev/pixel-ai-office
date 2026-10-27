from dataclasses import dataclass
from enum import StrEnum


class AgentRole(StrEnum):
    MANAGER = "manager"
    DEVELOPER = "developer"
    RESEARCHER = "researcher"


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    id: str
    name: str
    role: AgentRole
    description: str
    responsibilities: tuple[str, ...]
    system_instruction: str
