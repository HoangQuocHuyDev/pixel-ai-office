import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.schemas.ai import AIPromptRequest
from app.services import chat_service
from app.services.ai_service import AIService
from app.services.streaming_service import persistent_sse_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_service() -> AIService:
    return AIService()


async def sse_event_stream_generator(
    request: Request,
    ai_service: AIService,
    payload: AIPromptRequest,
) -> AsyncIterator[str]:
    async for event in persistent_sse_stream(
        request=request,
        chunks=ai_service.generate_response_stream(payload),
        conversation_id=payload.conversation_id,
    ):
        yield event


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream AI response",
    description="Streams AI responses chunk-by-chunk using Server-Sent Events (SSE).",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE event stream of chunks, followed by completion or error event.",
            "content": {"text/event-stream": {}},
        },
        404: {
            "description": "Conversation not found if conversation_id was provided.",
        },
        422: {
            "description": "Validation error for prompt or conversation_id.",
        },
        500: {
            "description": "Configuration or provider initialization error.",
        },
    },
)
def stream_ai_response(
    request: Request,
    payload: AIPromptRequest,
    ai_service: Annotated[AIService, Depends(get_ai_service)],
) -> StreamingResponse:
    # Validate provider initialization before initiating stream
    ai_service.ensure_ready()

    # If conversation_id is provided, verify conversation exists before starting stream
    if payload.conversation_id is not None:
        with SessionLocal() as db_session:
            chat_service.require_conversation_agent(
                db_session,
                payload.conversation_id,
                "manager",
            )

    return StreamingResponse(
        sse_event_stream_generator(request, ai_service, payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

