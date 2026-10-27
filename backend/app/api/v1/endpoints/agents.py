from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from app.agents.registry import default_agent_registry
from app.db.session import SessionLocal, get_db
from app.schemas.agent import (
    AgentActivityResponse, AgentMonitoringResponse, AgentMonitoringSummary,
    AgentPromptRequest, AgentPublicResponse, AgentTimelineResponse,
)
from app.schemas.ai import AIResponse
from app.services.agent_service import AgentService
from app.services import chat_service
from app.services.streaming_service import persistent_sse_stream
from app.services.agent_activity_service import list_agent_activities
from app.services.agent_monitoring_service import get_agent_monitoring, get_agent_timeline, get_monitoring_summary
from sqlalchemy.orm import Session

router = APIRouter(prefix="/agents", tags=["agents"])


def get_agent_service() -> AgentService:
    return AgentService()


@router.get("", response_model=list[AgentPublicResponse])
def list_agents() -> list[AgentPublicResponse]:
    return [
        AgentPublicResponse.from_definition(agent)
        for agent in default_agent_registry.list()
    ]


@router.get("/activities", response_model=list[AgentActivityResponse])
def agent_activities(db: Annotated[Session, Depends(get_db)]) -> list[AgentActivityResponse]:
    return list_agent_activities(db)


@router.get("/monitoring/summary", response_model=AgentMonitoringSummary)
def monitoring_summary(db: Annotated[Session, Depends(get_db)]) -> AgentMonitoringSummary:
    return get_monitoring_summary(db)


@router.get("/{agent_id}/monitoring", response_model=AgentMonitoringResponse)
def agent_monitoring(agent_id: str, db: Annotated[Session, Depends(get_db)]) -> AgentMonitoringResponse:
    return get_agent_monitoring(db, agent_id)


@router.get("/{agent_id}/timeline", response_model=AgentTimelineResponse)
def agent_timeline(
    agent_id: str,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentTimelineResponse:
    return get_agent_timeline(db, agent_id, limit, offset)


@router.get("/{agent_id}", response_model=AgentPublicResponse)
def get_agent(agent_id: str) -> AgentPublicResponse:
    return AgentPublicResponse.from_definition(default_agent_registry.get(agent_id))


@router.post("/{agent_id}/generate", response_model=AIResponse)
async def generate_agent_response(
    agent_id: str,
    payload: AgentPromptRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> AIResponse:
    return await agent_service.generate_response(agent_id, payload.prompt)


@router.post(
    "/{agent_id}/stream",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}},
        404: {"description": "Agent not found."},
        422: {"description": "Prompt validation error."},
    },
)
def stream_agent_response(
    request: Request,
    agent_id: str,
    payload: AgentPromptRequest,
    agent_service: Annotated[AgentService, Depends(get_agent_service)],
) -> StreamingResponse:
    default_agent_registry.get(agent_id)
    if payload.conversation_id is not None:
        with SessionLocal() as db_session:
            chat_service.require_conversation_agent(
                db_session,
                payload.conversation_id,
                agent_id,
            )
    agent_service.ensure_ready()
    return StreamingResponse(
        persistent_sse_stream(
            request=request,
            chunks=agent_service.generate_response_stream(agent_id, payload.prompt),
            conversation_id=payload.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
