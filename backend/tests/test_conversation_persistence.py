import json
from collections.abc import AsyncIterator
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1.endpoints.ai import get_ai_service
from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.ai import AIPromptRequest
from app.services import chat_service
from app.services.ai_service import AIService


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_list_messages_endpoint_success(client: TestClient) -> None:
    # 1. Create conversation
    conv = client.post("/api/v1/conversations", json={"title": "Message List Test"}).json()
    conv_id = conv["id"]

    try:
        # 2. Add user message
        msg1 = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "User message 1"},
        ).json()

        # 3. Add assistant message via service
        with SessionLocal() as db:
            msg2 = chat_service.create_assistant_message(
                db=db,
                conversation_id=conv_id,
                content="Assistant response 1",
            )
            msg2_id = msg2.id

        # 4. Fetch list via GET /api/v1/conversations/{conv_id}/messages
        res = client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert res.status_code == 200
        messages = res.json()
        assert len(messages) == 2
        assert messages[0]["id"] == msg1["id"]
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "User message 1"

        assert messages[1]["id"] == msg2_id
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Assistant response 1"

        # 5. Test pagination limit=1
        res_paginated = client.get(f"/api/v1/conversations/{conv_id}/messages?limit=1&offset=0")
        assert res_paginated.status_code == 200
        assert len(res_paginated.json()) == 1
        assert res_paginated.json()[0]["id"] == msg1["id"]

    finally:
        client.delete(f"/api/v1/conversations/{conv_id}")


def test_list_messages_returns_404_for_nonexistent_conversation(client: TestClient) -> None:
    res = client.get("/api/v1/conversations/9999999/messages")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_cannot_forge_assistant_role_via_public_api(client: TestClient) -> None:
    conv = client.post("/api/v1/conversations", json={"title": "Role Forgery Test"}).json()
    conv_id = conv["id"]

    try:
        # MessageCreate schema forbids extra fields (extra="forbid")
        res = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"content": "Hacked response", "role": "assistant"},
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

    finally:
        client.delete(f"/api/v1/conversations/{conv_id}")


def test_create_assistant_message_deduplication() -> None:
    with SessionLocal() as db:
        conv = chat_service.create_conversation(db, title="Deduplication Test")
        try:
            # First insert
            msg1 = chat_service.create_assistant_message(db, conv.id, "Unique content")
            # Duplicate insert with identical content
            msg2 = chat_service.create_assistant_message(db, conv.id, "Unique content")

            assert msg1.id == msg2.id

            # Verify only 1 message in DB
            stmt = select(Message).where(Message.conversation_id == conv.id)
            messages = db.scalars(stmt).all()
            assert len(messages) == 1
        finally:
            chat_service.delete_conversation(db, conv.id)


def test_ai_streaming_persists_assistant_message_on_success(client: TestClient) -> None:
    # Setup mock AI service
    class MockSuccessAIService(AIService):
        async def generate_response_stream(
            self, request: AIPromptRequest
        ) -> AsyncIterator[str]:
            yield "Plan: "
            yield "Step 1. "
            yield "Complete."

    mock_service = MockSuccessAIService()
    mock_service._get_provider = MagicMock()

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        conv = client.post("/api/v1/conversations", json={"title": "Stream Persist Test"}).json()
        conv_id = conv["id"]

        try:
            # Send stream request with conversation_id
            response = client.post(
                "/api/v1/ai/stream",
                json={
                    "prompt": "Create a roadmap",
                    "conversation_id": conv_id,
                },
            )
            assert response.status_code == 200

            # Parse SSE events
            events = []
            for line in response.text.split("\n"):
                if line.startswith("event: "):
                    event_type = line[len("event: "):].strip()
                elif line.startswith("data: "):
                    data = json.loads(line[len("data: "):])
                    events.append((event_type, data))

            # Verify done event contains message_id and conversation_id
            done_event = [e for e in events if e[0] == "done"][0]
            assert done_event[1]["status"] == "completed"
            assert done_event[1]["conversation_id"] == conv_id
            assert done_event[1]["message_id"] is not None

            # Verify message exists in PostgreSQL
            with SessionLocal() as db:
                stmt = select(Message).where(Message.id == done_event[1]["message_id"])
                saved_msg = db.scalars(stmt).first()
                assert saved_msg is not None
                assert saved_msg.role == "assistant"
                assert saved_msg.content == "Plan: Step 1. Complete."
                assert saved_msg.conversation_id == conv_id

        finally:
            client.delete(f"/api/v1/conversations/{conv_id}")

    finally:
        app.dependency_overrides.pop(get_ai_service, None)


def test_ai_streaming_does_not_persist_on_ai_error(client: TestClient) -> None:
    class MockErrorAIService(AIService):
        async def generate_response_stream(
            self, request: AIPromptRequest
        ) -> AsyncIterator[str]:
            yield "Partial text before error..."
            raise ApplicationError(
                status_code=502,
                error_code="AI_NETWORK_ERROR",
                message="Network failed",
            )

    mock_service = MockErrorAIService()
    mock_service._get_provider = MagicMock()

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        conv = client.post("/api/v1/conversations", json={"title": "Error No Persist Test"}).json()
        conv_id = conv["id"]

        try:
            response = client.post(
                "/api/v1/ai/stream",
                json={
                    "prompt": "Failing prompt",
                    "conversation_id": conv_id,
                },
            )
            assert response.status_code == 200

            # Verify error event emitted
            assert "event: error" in response.text

            # Verify NO assistant message was saved to database
            with SessionLocal() as db:
                stmt = select(Message).where(
                    Message.conversation_id == conv_id,
                    Message.role == "assistant",
                )
                saved_msgs = db.scalars(stmt).all()
                assert len(saved_msgs) == 0

        finally:
            client.delete(f"/api/v1/conversations/{conv_id}")

    finally:
        app.dependency_overrides.pop(get_ai_service, None)


def test_ai_streaming_rejects_nonexistent_conversation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ai/stream",
        json={
            "prompt": "Hello",
            "conversation_id": 9999999,
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

