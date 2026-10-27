import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import Request

from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.services import chat_service

logger = logging.getLogger(__name__)


async def persistent_sse_stream(
    request: Request,
    chunks: AsyncIterator[str],
    conversation_id: int | None = None,
) -> AsyncIterator[str]:
    accumulated_content = ""
    try:
        async for chunk in chunks:
            if await request.is_disconnected():
                logger.info("Client disconnected during AI streaming")
                return
            accumulated_content += chunk
            yield f"event: chunk\ndata: {json.dumps({'content': chunk})}\n\n"

        if await request.is_disconnected():
            return

        saved_message_id: int | None = None
        if conversation_id is not None and accumulated_content.strip():
            try:
                with SessionLocal() as db_session:
                    message = chat_service.create_assistant_message(
                        db=db_session,
                        conversation_id=conversation_id,
                        content=accumulated_content,
                    )
                    saved_message_id = message.id
            except Exception:
                logger.exception(
                    "Failed to persist assistant message to conversation %s",
                    conversation_id,
                )
                payload = json.dumps({
                    "code": "DB_PERSISTENCE_ERROR",
                    "message": "Assistant response generated but failed to persist to conversation.",
                })
                yield f"event: error\ndata: {payload}\n\n"
                return

        done_payload: dict[str, object] = {"status": "completed"}
        if conversation_id is not None:
            done_payload["message_id"] = saved_message_id
            done_payload["conversation_id"] = conversation_id
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
    except asyncio.CancelledError:
        logger.info("AI streaming cancelled")
        return
    except ApplicationError as exc:
        logger.warning("Application error during AI streaming: %s", exc.error_code)
        payload = json.dumps({"code": exc.error_code, "message": exc.message})
        yield f"event: error\ndata: {payload}\n\n"
    except Exception:
        logger.exception("Unexpected error during AI streaming")
        payload = json.dumps({
            "code": "AI_INTERNAL_ERROR",
            "message": "An unexpected error occurred during streaming.",
        })
        yield f"event: error\ndata: {payload}\n\n"
