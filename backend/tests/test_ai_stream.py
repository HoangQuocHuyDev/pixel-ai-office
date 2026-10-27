import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from app.ai.gemini_provider import GeminiProvider
from app.api.v1.endpoints.ai import get_ai_service
from app.core.exceptions import ApplicationError
from app.main import app
from app.schemas.ai import AIPromptRequest
from app.services.ai_service import AIService


class MockStreamChunk:
    def __init__(self, text: str) -> None:
        self.text = text


class MockAsyncStream:
    def __init__(
        self,
        chunks: list[str],
        fail_after: int = -1,
        error_to_raise: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.error_to_raise = error_to_raise
        self.index = 0

    def __aiter__(self) -> "MockAsyncStream":
        return self

    async def __anext__(self) -> MockStreamChunk:
        if self.fail_after >= 0 and self.index == self.fail_after:
            if self.error_to_raise:
                raise self.error_to_raise
            raise errors.APIError(
                code=500,
                response_json={"error": {"message": "Mid-stream error", "status": "INTERNAL"}},
            )

        if self.index < len(self.chunks):
            chunk = MockStreamChunk(self.chunks[self.index])
            self.index += 1
            return chunk

        raise StopAsyncIteration


def create_mock_streaming_client(
    chunks: list[str] | None = None,
    fail_on_init: Exception | None = None,
    fail_after_chunk: int = -1,
    fail_error: Exception | None = None,
) -> MagicMock:
    client = MagicMock()
    if fail_on_init:
        client.aio.models.generate_content_stream = AsyncMock(side_effect=fail_on_init)
    else:
        stream = MockAsyncStream(
            chunks=chunks if chunks is not None else ["Hello", " world", "!"],
            fail_after=fail_after_chunk,
            error_to_raise=fail_error,
        )
        client.aio.models.generate_content_stream = AsyncMock(return_value=stream)
    return client


# 1. Gemini Provider streaming success
@pytest.mark.anyio
async def test_gemini_provider_streaming_success() -> None:
    expected_chunks = ["Thinking...", " Found solution:", " 42"]
    mock_client = create_mock_streaming_client(chunks=expected_chunks)

    provider = GeminiProvider(
        api_key="valid-key",
        model="gemini-3.5-flash",
        client=mock_client,
    )

    received = []
    async for chunk in provider.generate_stream(prompt="What is the answer?"):
        received.append(chunk)

    assert received == expected_chunks


# 2. AIService forwards chunks in correct order
@pytest.mark.anyio
async def test_ai_service_forwards_stream_chunks_in_order() -> None:
    expected_chunks = ["Step 1", ", ", "Step 2", ", ", "Step 3"]
    mock_client = create_mock_streaming_client(chunks=expected_chunks)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    service = AIService(provider=provider)

    received = []
    async for chunk in service.generate_response_stream(
        AIPromptRequest(prompt="List steps", system_instruction="Be brief")
    ):
        received.append(chunk)

    assert received == expected_chunks


# 3. API SSE endpoint returns properly formatted Server-Sent Events
def test_api_sse_streaming_endpoint_success() -> None:
    mock_chunks = ["Autonomous", " agents", " active"]
    mock_client = create_mock_streaming_client(chunks=mock_chunks)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    mock_service = AIService(provider=provider)

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/stream",
                json={"prompt": "Status update"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "no-cache" in response.headers["cache-control"]

        lines = [line for line in response.text.split("\n") if line.strip()]

        # Parse chunks and verify events
        events: list[tuple[str, dict]] = []
        current_event = None
        for line in response.text.split("\n"):
            if line.startswith("event: "):
                current_event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
                events.append((current_event, data))
                current_event = None

        assert len(events) == 4
        assert events[0] == ("chunk", {"content": "Autonomous"})
        assert events[1] == ("chunk", {"content": " agents"})
        assert events[2] == ("chunk", {"content": " active"})
        assert events[3] == ("done", {"status": "completed"})
    finally:
        app.dependency_overrides.pop(get_ai_service, None)


# 4. Empty prompt rejected before stream starts (HTTP 422)
def test_api_stream_rejects_empty_prompt() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/stream",
            json={"prompt": "    "},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# 5. Provider returns error before first chunk (SSE error emitted, no done event)
def test_api_stream_provider_error_before_first_chunk() -> None:
    api_err = errors.APIError(
        code=404,
        response_json={"error": {"message": "Model not found", "status": "NOT_FOUND"}},
    )
    mock_client = create_mock_streaming_client(fail_on_init=api_err)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    mock_service = AIService(provider=provider)

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/stream",
                json={"prompt": "Trigger 404"},
            )

        assert response.status_code == 200
        body = response.text
        assert "event: error" in body
        assert "AI_MODEL_NOT_FOUND" in body
        assert "event: done" not in body
    finally:
        app.dependency_overrides.pop(get_ai_service, None)


# 6. Provider returns error mid-stream (chunk emitted, followed by error event, no done event)
def test_api_stream_provider_error_mid_stream() -> None:
    rate_limit_err = errors.APIError(
        code=429,
        response_json={"error": {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}},
    )
    mock_client = create_mock_streaming_client(
        chunks=["First chunk", "Second chunk"],
        fail_after_chunk=1,
        fail_error=rate_limit_err,
    )
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    mock_service = AIService(provider=provider)

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/stream",
                json={"prompt": "Trigger 429 mid stream"},
            )

        assert response.status_code == 200
        body = response.text
        assert "event: chunk" in body
        assert "First chunk" in body
        assert "event: error" in body
        assert "AI_RATE_LIMIT_EXCEEDED" in body
        assert "event: done" not in body
    finally:
        app.dependency_overrides.pop(get_ai_service, None)


# 7. Client cancellation handled cleanly
@pytest.mark.anyio
async def test_stream_cancellation_handled_cleanly() -> None:
    async def infinite_chunks() -> AsyncIterator[str]:
        yield "Chunk 1"
        yield "Chunk 2"
        await asyncio.sleep(10)
        yield "Never reached"

    mock_provider = MagicMock()
    mock_provider.generate_stream = MagicMock(return_value=infinite_chunks())
    service = AIService(provider=mock_provider)

    stream_gen = service.generate_response_stream(AIPromptRequest(prompt="Test"))

    # Read one chunk then cancel
    c1 = await stream_gen.__anext__()
    assert c1 == "Chunk 1"
    await stream_gen.aclose()


# 8. No done event emitted after error
def test_no_done_event_after_error() -> None:
    mock_client = create_mock_streaming_client(
        chunks=["OK"],
        fail_after_chunk=1,
        fail_error=httpx.ConnectError("Connection dropped"),
    )
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    mock_service = AIService(provider=provider)

    app.dependency_overrides[get_ai_service] = lambda: mock_service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/stream",
                json={"prompt": "Network fail"},
            )
        body = response.text
        assert "event: error" in body
        assert "AI_NETWORK_ERROR" in body
        assert "event: done" not in body
    finally:
        app.dependency_overrides.pop(get_ai_service, None)


# 9. Non-streaming method from TASK 11 remains functional
@pytest.mark.anyio
async def test_non_streaming_method_remains_functional() -> None:
    from tests.test_ai import MockGenerateContentResponse

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=MockGenerateContentResponse(text="Non-streaming response")
    )
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    service = AIService(provider=provider)

    res = await service.generate_response(AIPromptRequest(prompt="Non streaming test"))
    assert res.content == "Non-streaming response"
    assert res.provider == "gemini"

