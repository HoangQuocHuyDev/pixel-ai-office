from typing import Literal

from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    backend_status: Literal["ok"]
    database_status: Literal["connected", "unavailable"]
    ai_provider: str
    ai_model: str
    api_key_configured: bool
    ai_configuration_status: Literal["configured", "missing"]
    application_mode: Literal["local-first"]
    application_name: str
    backend_version: str
    agents_count: int
