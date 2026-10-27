from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.models.conversation import Conversation
from app.models.message import Message
from app.agents.registry import default_agent_registry


def create_conversation(
    db: Session,
    title: str,
    agent_id: str = "manager",
) -> Conversation:
    agent = default_agent_registry.get(agent_id)
    conversation = Conversation(title=title, agent_id=agent.id)
    try:
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    except Exception:
        db.rollback()
        raise


def list_conversations(
    db: Session, limit: int = 20, offset: int = 0
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def get_conversation_by_id(db: Session, conversation_id: int) -> Conversation:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ApplicationError(
            status_code=404,
            error_code="CONVERSATION_NOT_FOUND",
            message=f"Conversation {conversation_id} not found.",
        )
    return conversation


def require_conversation_agent(
    db: Session,
    conversation_id: int,
    agent_id: str,
) -> Conversation:
    agent = default_agent_registry.get(agent_id)
    conversation = get_conversation_by_id(db, conversation_id)
    if conversation.agent_id != agent.id:
        raise ApplicationError(
            status_code=409,
            error_code="CONVERSATION_AGENT_MISMATCH",
            message=(
                f"Conversation {conversation_id} belongs to agent "
                f"'{conversation.agent_id}', not '{agent.id}'."
            ),
        )
    return conversation


def create_user_message(
    db: Session, conversation_id: int, content: str
) -> Message:
    # Verify conversation exists
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ApplicationError(
            status_code=404,
            error_code="CONVERSATION_NOT_FOUND",
            message=f"Conversation {conversation_id} not found.",
        )

    message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
    )
    conversation.updated_at = datetime.now(timezone.utc)

    try:
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise


def delete_conversation(db: Session, conversation_id: int) -> None:
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ApplicationError(
            status_code=404,
            error_code="CONVERSATION_NOT_FOUND",
            message=f"Conversation {conversation_id} not found.",
        )

    try:
        db.delete(conversation)
        db.commit()
    except Exception:
        db.rollback()
        raise


def list_messages(
    db: Session, conversation_id: int, limit: int = 100, offset: int = 0
) -> list[Message]:
    stmt_conv = select(Conversation).where(Conversation.id == conversation_id)
    if db.scalars(stmt_conv).first() is None:
        raise ApplicationError(
            status_code=404,
            error_code="CONVERSATION_NOT_FOUND",
            message=f"Conversation {conversation_id} not found.",
        )

    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def create_assistant_message(
    db: Session, conversation_id: int, content: str
) -> Message:
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    conversation = db.scalars(stmt).first()
    if conversation is None:
        raise ApplicationError(
            status_code=404,
            error_code="CONVERSATION_NOT_FOUND",
            message=f"Conversation {conversation_id} not found.",
        )

    trimmed = content.strip()
    if not trimmed:
        raise ApplicationError(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="Assistant message content cannot be empty.",
        )

    # De-duplication check: if latest message in conversation is already identical assistant message
    latest_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    latest_msg = db.scalars(latest_stmt).first()
    if latest_msg and latest_msg.role == "assistant" and latest_msg.content == trimmed:
        return latest_msg

    message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=trimmed,
    )
    conversation.updated_at = datetime.now(timezone.utc)

    try:
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise


