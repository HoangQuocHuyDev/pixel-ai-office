import json
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.api.v1.endpoints.agents import get_agent_service
from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.message import Message
from app.schemas.ai import AIPromptRequest, AIResponse
from app.services.agent_service import AgentService


class MockAIService:
    def __init__(self, chunks: list[str], error: ApplicationError | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.requests: list[AIPromptRequest] = []

    def ensure_ready(self) -> None:
        pass

    async def generate_response(self, request: AIPromptRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(provider="mock", model="mock", content="response")

    async def generate_response_stream(self, request: AIPromptRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


def parse_events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event_name = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event_name, json.loads(line.removeprefix("data: "))))
    return events


def test_migrated_column_defaults_legacy_rows_to_manager() -> None:
    with engine.begin() as connection:
        row = connection.execute(
            text("INSERT INTO conversations (title) VALUES (:title) RETURNING id, agent_id"),
            {"title": "Legacy default verification"},
        ).one()
        assert row.agent_id == "manager"
        connection.execute(
            text("DELETE FROM conversations WHERE id = :id"),
            {"id": row.id},
        )


def test_conversation_creation_and_history_are_agent_aware() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/conversations",
            json={"title": "Developer thread", "agent_id": "developer"},
        )
        assert created.status_code == 201
        conversation = created.json()
        try:
            assert conversation["agent_id"] == "developer"
            listed = client.get("/api/v1/conversations").json()
            assert next(item for item in listed if item["id"] == conversation["id"])["agent_id"] == "developer"
        finally:
            client.delete(f"/api/v1/conversations/{conversation['id']}")


def test_conversation_rejects_unknown_agent() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/conversations",
            json={"title": "Invalid", "agent_id": "unknown-agent"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_agent_mismatch_rejected_before_stream() -> None:
    mock = MockAIService(["should not run"])
    service = AgentService(ai_service=mock)  # type: ignore[arg-type]
    app.dependency_overrides[get_agent_service] = lambda: service
    try:
        with TestClient(app) as client:
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Manager only", "agent_id": "manager"},
            ).json()
            try:
                response = client.post(
                    "/api/v1/agents/developer/stream",
                    json={"prompt": "Wrong agent", "conversation_id": conversation["id"]},
                )
            finally:
                client.delete(f"/api/v1/conversations/{conversation['id']}")
    finally:
        app.dependency_overrides.pop(get_agent_service, None)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_AGENT_MISMATCH"
    assert mock.requests == []


def test_agent_stream_persists_once_and_uses_role_instruction() -> None:
    mock = MockAIService(["Developer ", "answer"])
    service = AgentService(ai_service=mock)  # type: ignore[arg-type]
    app.dependency_overrides[get_agent_service] = lambda: service
    try:
        with TestClient(app) as client:
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Coding", "agent_id": "developer"},
            ).json()
            try:
                payload = {"prompt": "Build it", "conversation_id": conversation["id"]}
                first = client.post("/api/v1/agents/developer/stream", json=payload)
                second = client.post("/api/v1/agents/developer/stream", json=payload)
                events = parse_events(first.text)
                done = next(data for name, data in events if name == "done")
                assert done["conversation_id"] == conversation["id"]
                assert done["message_id"] is not None

                with SessionLocal() as db:
                    messages = list(db.scalars(select(Message).where(
                        Message.conversation_id == conversation["id"],
                        Message.role == "assistant",
                    )).all())
                assert len(messages) == 1
                assert messages[0].content == "Developer answer"
                assert "correctness" in (mock.requests[0].system_instruction or "")
                assert next(data for name, data in parse_events(second.text) if name == "done")["message_id"] == messages[0].id
            finally:
                client.delete(f"/api/v1/conversations/{conversation['id']}")
    finally:
        app.dependency_overrides.pop(get_agent_service, None)


def test_failed_agent_stream_does_not_persist_assistant() -> None:
    mock = MockAIService(
        ["partial"],
        ApplicationError(502, "AI_NETWORK_ERROR", "Network failed"),
    )
    service = AgentService(ai_service=mock)  # type: ignore[arg-type]
    app.dependency_overrides[get_agent_service] = lambda: service
    try:
        with TestClient(app) as client:
            conversation = client.post(
                "/api/v1/conversations",
                json={"title": "Research", "agent_id": "researcher"},
            ).json()
            try:
                response = client.post(
                    "/api/v1/agents/researcher/stream",
                    json={"prompt": "Investigate", "conversation_id": conversation["id"]},
                )
                assert "event: error" in response.text
                assert "event: done" not in response.text
                with SessionLocal() as db:
                    saved = list(db.scalars(select(Message).where(
                        Message.conversation_id == conversation["id"],
                        Message.role == "assistant",
                    )).all())
                assert saved == []
            finally:
                client.delete(f"/api/v1/conversations/{conversation['id']}")
    finally:
        app.dependency_overrides.pop(get_agent_service, None)
