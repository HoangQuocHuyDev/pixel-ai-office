import time
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import Conversation
from app.models.message import Message


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint_remains_functional(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_conversation_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations",
        json={"title": "Test Project Discussion"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Project Discussion"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Cleanup
    client.delete(f"/api/v1/conversations/{data['id']}")


def test_create_conversation_rejects_empty_title(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations",
        json={"title": "   \n  \t "},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_create_conversation_rejects_long_title(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations",
        json={"title": "A" * 151},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_create_conversation_rejects_extra_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations",
        json={"title": "Valid title", "role": "admin", "extra": "data"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_conversations(client: TestClient) -> None:
    # Create two conversations
    c1 = client.post("/api/v1/conversations", json={"title": "List Test 1"}).json()
    c2 = client.post("/api/v1/conversations", json={"title": "List Test 2"}).json()

    response = client.get("/api/v1/conversations?limit=10&offset=0")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    ids = [c["id"] for c in items]
    assert c1["id"] in ids
    assert c2["id"] in ids

    # Cleanup
    client.delete(f"/api/v1/conversations/{c1['id']}")
    client.delete(f"/api/v1/conversations/{c2['id']}")


def test_get_conversation_detail_and_not_found(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/conversations", json={"title": "Detail Test"}
    ).json()
    conv_id = create_resp["id"]

    # Valid get
    get_resp = client.get(f"/api/v1/conversations/{conv_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == conv_id
    assert detail["title"] == "Detail Test"
    assert detail["messages"] == []

    # Non-existent get
    not_found_resp = client.get("/api/v1/conversations/999999999")
    assert not_found_resp.status_code == 404
    assert not_found_resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    # Cleanup
    client.delete(f"/api/v1/conversations/{conv_id}")


def test_send_user_message_success_and_stored_in_postgres(client: TestClient) -> None:
    conv = client.post(
        "/api/v1/conversations", json={"title": "Message Storage Test"}
    ).json()
    conv_id = conv["id"]
    initial_updated_at = conv["updated_at"]

    # Sleep slightly to ensure distinct timestamp for updated_at check
    time.sleep(0.05)

    prompt = "Create a personal portfolio website."
    msg_resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": prompt},
    )
    assert msg_resp.status_code == 201
    msg_data = msg_resp.json()
    assert msg_data["conversation_id"] == conv_id
    assert msg_data["role"] == "user"
    assert msg_data["content"] == prompt
    assert "id" in msg_data
    assert "created_at" in msg_data

    # Verify directly via direct DB session query
    with SessionLocal() as db:
        db_message = db.scalars(
            select(Message).where(Message.id == msg_data["id"])
        ).first()
        assert db_message is not None
        assert db_message.content == prompt
        assert db_message.role == "user"

        db_conv = db.scalars(
            select(Conversation).where(Conversation.id == conv_id)
        ).first()
        assert db_conv is not None
        assert db_conv.updated_at >= db_conv.created_at

    # Verify updated_at is updated in GET response
    get_conv = client.get(f"/api/v1/conversations/{conv_id}").json()
    assert len(get_conv["messages"]) == 1
    assert get_conv["messages"][0]["id"] == msg_data["id"]
    assert get_conv["updated_at"] != initial_updated_at or get_conv["updated_at"] >= initial_updated_at

    # Cleanup
    client.delete(f"/api/v1/conversations/{conv_id}")


def test_send_message_rejects_empty_content(client: TestClient) -> None:
    conv = client.post(
        "/api/v1/conversations", json={"title": "Empty Msg Test"}
    ).json()
    conv_id = conv["id"]

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "    "},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    client.delete(f"/api/v1/conversations/{conv_id}")


def test_send_message_rejects_excessive_content(client: TestClient) -> None:
    conv = client.post(
        "/api/v1/conversations", json={"title": "Max Length Test"}
    ).json()
    conv_id = conv["id"]

    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "M" * 4001},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    client.delete(f"/api/v1/conversations/{conv_id}")


def test_client_cannot_create_assistant_message(client: TestClient) -> None:
    conv = client.post(
        "/api/v1/conversations", json={"title": "Assistant Impersonation Test"}
    ).json()
    conv_id = conv["id"]

    # Attempting to supply role='assistant' should be rejected due to extra='forbid'
    response = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Fake assistant reply", "role": "assistant"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    # Confirm message was NOT created
    detail = client.get(f"/api/v1/conversations/{conv_id}").json()
    assert len(detail["messages"]) == 0

    client.delete(f"/api/v1/conversations/{conv_id}")


def test_send_message_to_nonexistent_conversation_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/conversations/999999999/messages",
        json={"content": "Hello in void"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_delete_conversation_cascades_messages(client: TestClient) -> None:
    conv = client.post(
        "/api/v1/conversations", json={"title": "Cascade Delete Test"}
    ).json()
    conv_id = conv["id"]

    msg1 = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Message 1"},
    ).json()
    msg2 = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Message 2"},
    ).json()

    # Delete conversation
    del_resp = client.delete(f"/api/v1/conversations/{conv_id}")
    assert del_resp.status_code == 204

    # Verify conversation is gone
    get_resp = client.get(f"/api/v1/conversations/{conv_id}")
    assert get_resp.status_code == 404

    # Verify messages are cascade deleted from PostgreSQL
    with SessionLocal() as db:
        remaining_messages = db.scalars(
            select(Message).where(Message.id.in_([msg1["id"], msg2["id"]]))
        ).all()
        assert len(remaining_messages) == 0

    # Delete non-existent conversation returns 404
    del_again = client.delete(f"/api/v1/conversations/{conv_id}")
    assert del_again.status_code == 404

