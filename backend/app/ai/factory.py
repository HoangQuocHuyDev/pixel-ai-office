from typing import Any

from app.ai.base import BaseAIProvider
from app.ai.gemini_provider import GeminiProvider
from app.core.config import get_settings
from app.core.exceptions import ApplicationError


def get_ai_provider(
    provider_name: str | None = None,
    **overrides: Any,
) -> BaseAIProvider:
    settings = get_settings()
    active_provider = (provider_name or settings.ai_provider).strip().lower()

    if active_provider == "gemini":
        if "api_key" in overrides:
            api_key = overrides["api_key"]
            if isinstance(api_key, str):
                api_key = api_key.strip()
        else:
            api_key = (
                settings.gemini_api_key.get_secret_value().strip()
                if settings.gemini_api_key
                else None
            )

        if not api_key:
            raise ApplicationError(
                status_code=500,
                error_code="AI_CONFIG_ERROR",
                message="GEMINI_API_KEY is not configured.",
            )

        model = overrides.get("model") or settings.gemini_model
        timeout = overrides.get("timeout_seconds") or settings.ai_request_timeout_seconds
        max_tokens = overrides.get("max_output_tokens") or settings.ai_max_output_tokens
        client = overrides.get("client")

        return GeminiProvider(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
            max_output_tokens=max_tokens,
            client=client,
        )

    raise ApplicationError(
        status_code=500,
        error_code="AI_CONFIG_ERROR",
        message=f"Unsupported AI provider: '{active_provider}'. Only 'gemini' is supported.",
    )
