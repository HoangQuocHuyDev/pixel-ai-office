from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.registry import default_agent_registry
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.system import SystemStatusResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Annotated[Session, Depends(get_db)]) -> SystemStatusResponse:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database_status = "connected"
    except SQLAlchemyError:
        database_status = "unavailable"
    configured = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip())
    return SystemStatusResponse(
        backend_status="ok", database_status=database_status,
        ai_provider="Google Gemini", ai_model=settings.gemini_model,
        api_key_configured=configured, ai_configuration_status="configured" if configured else "missing",
        application_mode="local-first", application_name=settings.app_name,
        backend_version=settings.app_version, agents_count=len(default_agent_registry.list()),
    )
