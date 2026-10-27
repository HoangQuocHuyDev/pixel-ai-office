import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from google.genai import errors

from app.ai.factory import get_ai_provider
from app.ai.gemini_provider import GeminiProvider
from app.core.exceptions import ApplicationError
from app.schemas.ai import AIPromptRequest
from app.schemas.planning import PlanProposal
from app.services.ai_service import AIService


class MockGenerateContentResponse:
    def __init__(
        self,
        text: str | None = "Mock AI response",
        prompt_tokens: int = 12,
        candidate_tokens: int = 24,
        finish_reason: str = "STOP",
    ) -> None:
        self.text = text
        self.usage_metadata = SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=candidate_tokens,
            total_token_count=prompt_tokens + candidate_tokens,
        )
        self.candidates = [SimpleNamespace(finish_reason=finish_reason)]


def create_mock_gemini_client(
    response: Any = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    client = MagicMock()
    mock_generate = AsyncMock()
    if side_effect:
        mock_generate.side_effect = side_effect
    else:
        mock_generate.return_value = response or MockGenerateContentResponse()
    client.aio.models.generate_content = mock_generate
    return client


# 1. Valid prompt & successful normalized response
@pytest.mark.anyio
async def test_gemini_generate_success_normalized_response() -> None:
    mock_resp = MockGenerateContentResponse(
        text="Plan: 1. Architecture, 2. Frontend, 3. Testing.",
        prompt_tokens=15,
        candidate_tokens=30,
        finish_reason="STOP",
    )
    mock_client = create_mock_gemini_client(response=mock_resp)
    provider = GeminiProvider(
        api_key="test-api-key",
        model="gemini-2.5-flash",
        client=mock_client,
    )
    service = AIService(provider=provider)

    req = AIPromptRequest(
        prompt="Create a project plan",
        system_instruction="You are Manager AI",
    )
    res = await service.generate_response(req)

    assert res.provider == "gemini"
    assert res.model == "gemini-2.5-flash"
    assert "Plan: 1. Architecture" in res.content
    assert res.usage_metadata is not None
    assert res.usage_metadata["prompt_token_count"] == 15
    assert res.usage_metadata["candidates_token_count"] == 30
    assert res.usage_metadata["total_token_count"] == 45
    assert res.finish_reason == "STOP"


# 2. Empty prompt rejected
def test_empty_prompt_rejected_by_schema() -> None:
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        AIPromptRequest(prompt="    \n   ")


# 3. Provider factory works & supports model override
def test_provider_factory_configuration() -> None:
    mock_client = create_mock_gemini_client()
    provider = get_ai_provider(
        provider_name="gemini",
        api_key="custom-key",
        model="gemini-1.5-pro",
        timeout_seconds=45.0,
        client=mock_client,
    )
    assert provider.provider_name == "gemini"
    assert provider.model_name == "gemini-1.5-pro"


# 4. Missing API key raises config error
def test_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ApplicationError) as exc_info:
        get_ai_provider(provider_name="gemini", api_key="")
    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "AI_CONFIG_ERROR"


# 5. Invalid API key / Authentication failure
@pytest.mark.anyio
async def test_gemini_authentication_error() -> None:
    api_err = errors.APIError(
        code=401,
        response_json={"error": {"message": "API key not valid", "status": "UNAUTHENTICATED"}},
    )
    mock_client = create_mock_gemini_client(side_effect=api_err)
    provider = GeminiProvider(api_key="bad-key", client=mock_client)
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Hello"))
    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "AI_AUTHENTICATION_ERROR"
    assert "bad-key" not in exc_info.value.message


# 6. Request Timeout
@pytest.mark.anyio
async def test_gemini_timeout_error() -> None:
    async def slow_call(*_args: Any, **_kwargs: Any) -> Any:
        await asyncio.sleep(0.5)
        return MockGenerateContentResponse()

    mock_client = MagicMock()
    mock_client.aio.models.generate_content.side_effect = slow_call

    provider = GeminiProvider(
        api_key="valid-key",
        timeout_seconds=0.05,
        client=mock_client,
    )
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Timeout test"))
    assert exc_info.value.status_code == 504
    assert exc_info.value.error_code == "AI_REQUEST_TIMEOUT"


# 7. Rate limit / Quota exceeded (429)
@pytest.mark.anyio
async def test_gemini_rate_limit_or_quota_exceeded() -> None:
    api_err = errors.APIError(
        code=429,
        response_json={"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}},
    )
    mock_client = create_mock_gemini_client(side_effect=api_err)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Rate test"))
    assert exc_info.value.status_code == 429
    assert exc_info.value.error_code == "AI_RATE_LIMIT_EXCEEDED"


# 8. Model not found (404)
@pytest.mark.anyio
async def test_gemini_model_not_found() -> None:
    api_err = errors.APIError(
        code=404,
        response_json={"error": {"message": "models/unknown-model is not found", "status": "NOT_FOUND"}},
    )
    mock_client = create_mock_gemini_client(side_effect=api_err)
    provider = GeminiProvider(api_key="valid-key", model="unknown-model", client=mock_client)
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Hello"))
    assert exc_info.value.status_code == 500
    assert exc_info.value.error_code == "AI_MODEL_NOT_FOUND"


# 9. Network error
@pytest.mark.anyio
async def test_gemini_network_error() -> None:
    net_err = httpx.ConnectError("Connection failed to Google APIs")
    mock_client = create_mock_gemini_client(side_effect=net_err)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Network test"))
    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "AI_NETWORK_ERROR"


# 10. Empty response from model
@pytest.mark.anyio
async def test_gemini_empty_response_handling() -> None:
    empty_resp = MockGenerateContentResponse(text="")
    mock_client = create_mock_gemini_client(response=empty_resp)
    provider = GeminiProvider(api_key="valid-key", client=mock_client)
    service = AIService(provider=provider)

    with pytest.raises(ApplicationError) as exc_info:
        await service.generate_response(AIPromptRequest(prompt="Prompt returning empty"))
    assert exc_info.value.status_code == 502
    assert exc_info.value.error_code == "AI_EMPTY_RESPONSE"


# 11. Security: API key not leaked in logs or error messages
@pytest.mark.anyio
async def test_security_api_key_not_leaked(caplog: pytest.LogCaptureFixture) -> None:
    secret_key = "super-secret-gemini-key-12345"
    api_err = errors.APIError(
        code=401,
        response_json={"error": {"message": "Invalid auth", "status": "UNAUTHENTICATED"}},
    )
    mock_client = create_mock_gemini_client(side_effect=api_err)
    provider = GeminiProvider(api_key=secret_key, client=mock_client)
    service = AIService(provider=provider)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApplicationError) as exc_info:
            await service.generate_response(AIPromptRequest(prompt="Secret leak test"))

    assert secret_key not in exc_info.value.message
    for record in caplog.records:
        assert secret_key not in record.getMessage()


@pytest.mark.anyio
async def test_structured_generation_uses_json_schema_for_forbid_extra_models() -> None:
    proposal = {
        "title": "Portfolio website",
        "objective": "Build a modern portfolio website.",
        "tasks": [{
            "title": "Implement portfolio",
            "description": "Build responsive project and contact sections.",
            "priority": "high",
            "assigned_agent_id": "developer",
            "sequence_order": 1,
        }],
    }
    response = MockGenerateContentResponse(text="unused")
    response.parsed = proposal
    mock_client = create_mock_gemini_client(response=response)
    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash", client=mock_client)

    result = await provider.generate_structured("Create a plan", PlanProposal)

    assert isinstance(result, PlanProposal)
    call_config = mock_client.aio.models.generate_content.await_args.kwargs["config"]
    assert call_config.response_mime_type == "application/json"
    assert call_config.response_schema is None
    assert call_config.response_json_schema["additionalProperties"] is False
    assert call_config.response_json_schema["$defs"]["PlannedTask"]["additionalProperties"] is False


def test_gemini_503_preserves_retry_after_metadata() -> None:
    response = httpx.Response(503, headers={"Retry-After": "7"})
    error = errors.APIError(503, {"error": {"message": "Unavailable", "status": "UNAVAILABLE"}}, response)
    provider = GeminiProvider(api_key="test-api-key", client=create_mock_gemini_client())
    with pytest.raises(ApplicationError) as raised:
        provider._handle_api_error(error)
    assert raised.value.status_code == 503
    assert raised.value.error_code == "AI_PROVIDER_ERROR"
    assert raised.value.retry_after_seconds == 7
