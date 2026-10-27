from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
)
from app.schemas.message import MessageCreate, MessageResponse
from app.services import chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationResponse,
    summary="Create a new conversation",
    description="Creates a new conversation container for user requests.",
)
def create_conversation(
    payload: ConversationCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ConversationResponse:
    return chat_service.create_conversation(
        db=db,
        title=payload.title,
        agent_id=payload.agent_id,
    )


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[ConversationResponse],
    summary="List conversations",
    description="Returns a paginated list of conversations ordered by most recently updated.",
)
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of items to return")] = 20,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
) -> list[ConversationResponse]:
    return chat_service.list_conversations(db=db, limit=limit, offset=offset)


@router.get(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    response_model=ConversationDetailResponse,
    summary="Get conversation details",
    description="Retrieves a conversation and all its messages ordered chronologically.",
)
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ConversationDetailResponse:
    return chat_service.get_conversation_by_id(db=db, conversation_id=conversation_id)


@router.get(
    "/{conversation_id}/messages",
    status_code=status.HTTP_200_OK,
    response_model=list[MessageResponse],
    summary="List messages in a conversation",
    description="Retrieves messages for a conversation ordered chronologically.",
)
def list_messages(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of items to return")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
) -> list[MessageResponse]:
    return chat_service.list_messages(
        db=db,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageResponse,
    summary="Send a user message",
    description="Appends a new user message to the conversation and updates the conversation timestamp.",
)
def create_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    return chat_service.create_user_message(
        db=db,
        conversation_id=conversation_id,
        content=payload.content,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
    description="Permanently deletes the conversation and cascades to all its messages.",
)
def delete_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    chat_service.delete_conversation(db=db, conversation_id=conversation_id)

