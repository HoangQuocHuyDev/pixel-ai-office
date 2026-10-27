import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from google import genai
from google.genai import errors, types

from app.ai.base import BaseAIProvider
from app.core.exceptions import ApplicationError
from app.schemas.ai import AIResponse

logger = logging.getLogger(__name__)
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class GeminiProvider(BaseAIProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = 30.0,
        max_output_tokens: int = 2048,
        client: genai.Client | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ApplicationError(
                status_code=500,
                error_code="AI_CONFIG_ERROR",
                message="GEMINI_API_KEY is not configured.",
            )

        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._client = client or genai.Client(api_key=api_key.strip())

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> AIResponse:
        config_args: dict[str, Any] = {
            "max_output_tokens": self._max_output_tokens,
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_args)

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Gemini API request timed out after %s seconds", self._timeout_seconds)
            raise ApplicationError(
                status_code=504,
                error_code="AI_REQUEST_TIMEOUT",
                message=f"Gemini API request timed out after {self._timeout_seconds} seconds.",
            )
        except errors.APIError as exc:
            logger.error("Gemini API error code=%s", exc.code)
            self._handle_api_error(exc)
        except Exception as exc:
            exc_name = type(exc).__name__.lower()
            if any(term in exc_name for term in ["connect", "network", "socket", "http"]):
                logger.warning("Gemini network connection failed: %s", type(exc).__name__)
                raise ApplicationError(
                    status_code=502,
                    error_code="AI_NETWORK_ERROR",
                    message="Failed to connect to Gemini API network endpoint.",
                )
            logger.exception("Unexpected error during Gemini generation")
            raise ApplicationError(
                status_code=500,
                error_code="AI_INTERNAL_ERROR",
                message="An unexpected error occurred during AI content generation.",
            )

        # Validate content extraction
        content = getattr(response, "text", None)
        if not content or not str(content).strip():
            logger.warning("Gemini returned an empty response")
            raise ApplicationError(
                status_code=502,
                error_code="AI_EMPTY_RESPONSE",
                message="Received an empty response from Gemini model.",
            )

        # Extract usage metadata safely
        usage_dict: dict[str, Any] | None = None
        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            usage_dict = {
                "prompt_token_count": getattr(usage_meta, "prompt_token_count", None),
                "candidates_token_count": getattr(usage_meta, "candidates_token_count", None),
                "total_token_count": getattr(usage_meta, "total_token_count", None),
            }

        # Extract finish reason if available
        finish_reason: str | None = None
        candidates = getattr(response, "candidates", None)
        if candidates and len(candidates) > 0:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            if finish_reason is not None:
                finish_reason = str(finish_reason)

        return AIResponse(
            provider=self.provider_name,
            model=self._model,
            content=str(content),
            usage_metadata=usage_dict,
            finish_reason=finish_reason,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> AsyncIterator[str]:
        config_args: dict[str, Any] = {
            "max_output_tokens": self._max_output_tokens,
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        config = types.GenerateContentConfig(**config_args)

        try:
            stream = await asyncio.wait_for(
                self._client.aio.models.generate_content_stream(
                    model=self._model,
                    contents=prompt,
                    config=config,
                ),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Gemini API streaming setup timed out after %s seconds",
                self._timeout_seconds,
            )
            raise ApplicationError(
                status_code=504,
                error_code="AI_REQUEST_TIMEOUT",
                message=f"Gemini API request timed out after {self._timeout_seconds} seconds.",
            )
        except errors.APIError as exc:
            logger.error("Gemini API stream error code=%s", exc.code)
            self._handle_api_error(exc)
        except Exception as exc:
            exc_name = type(exc).__name__.lower()
            if any(term in exc_name for term in ["connect", "network", "socket", "http"]):
                logger.warning("Gemini network connection failed during stream setup: %s", type(exc).__name__)
                raise ApplicationError(
                    status_code=502,
                    error_code="AI_NETWORK_ERROR",
                    message="Failed to connect to Gemini API network endpoint.",
                )
            logger.exception("Unexpected error during Gemini stream initialization")
            raise ApplicationError(
                status_code=500,
                error_code="AI_INTERNAL_ERROR",
                message="An unexpected error occurred during AI content generation.",
            )

        try:
            async for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield str(text)
        except asyncio.CancelledError:
            logger.info("Gemini stream iteration cancelled")
            raise
        except errors.APIError as exc:
            logger.error("Gemini API error during stream iteration code=%s", exc.code)
            self._handle_api_error(exc)
        except Exception as exc:
            exc_name = type(exc).__name__.lower()
            if any(term in exc_name for term in ["connect", "network", "socket", "http"]):
                logger.warning("Gemini network connection failed during stream iteration: %s", type(exc).__name__)
                raise ApplicationError(
                    status_code=502,
                    error_code="AI_NETWORK_ERROR",
                    message="Failed to connect to Gemini API network endpoint.",
                )
            logger.exception("Unexpected error during Gemini stream iteration")
            raise ApplicationError(
                status_code=500,
                error_code="AI_INTERNAL_ERROR",
                message="An unexpected error occurred during AI content generation.",
            )

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[StructuredModel],
        system_instruction: str | None = None,
    ) -> StructuredModel:
        config_args: dict[str, Any] = {
            "max_output_tokens": self._max_output_tokens,
            "response_mime_type": "application/json",
            # PlanProposal uses extra="forbid", which emits
            # additionalProperties=false. google-genai's JSON Schema path
            # supports that keyword; the OpenAPI response_schema path does not
            # for the configured Gemini model.
            "response_json_schema": response_schema.model_json_schema(),
        }
        if system_instruction:
            config_args["system_instruction"] = system_instruction
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_args),
                ),
                timeout=self._timeout_seconds,
            )
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                raise ApplicationError(502, "AI_INVALID_STRUCTURED_OUTPUT", "Gemini did not return structured planning data.")
            return response_schema.model_validate(parsed)
        except ValidationError as exc:
            logger.warning("Gemini structured response failed schema validation")
            raise ApplicationError(502, "AI_INVALID_STRUCTURED_OUTPUT", "Gemini returned invalid planning data.") from exc
        except asyncio.TimeoutError:
            raise ApplicationError(504, "AI_REQUEST_TIMEOUT", f"Gemini API request timed out after {self._timeout_seconds} seconds.")
        except ApplicationError:
            raise
        except errors.APIError as exc:
            self._handle_api_error(exc)
        except Exception as exc:
            logger.exception("Unexpected structured generation error")
            raise ApplicationError(500, "AI_INTERNAL_ERROR", "An unexpected error occurred during AI content generation.") from exc

    def _handle_api_error(self, exc: errors.APIError) -> None:
        code = exc.code
        retry_after = self._retry_after_seconds(exc)
        if code in (401, 403):
            raise ApplicationError(
                status_code=500,
                error_code="AI_AUTHENTICATION_ERROR",
                message="Authentication failed with Gemini API. Check GEMINI_API_KEY.",
            )
        if code == 404:
            raise ApplicationError(
                status_code=500,
                error_code="AI_MODEL_NOT_FOUND",
                message=f"Gemini model '{self._model}' was not found or is unavailable.",
            )
        if code == 429:
            raise ApplicationError(
                status_code=429,
                error_code="AI_RATE_LIMIT_EXCEEDED",
                message="Gemini API quota or rate limit exceeded.",
                retry_after_seconds=retry_after,
            )
        if code == 400:
            raise ApplicationError(
                status_code=400,
                error_code="AI_BAD_REQUEST",
                message="Invalid request parameters to Gemini API.",
            )
        if code >= 500:
            raise ApplicationError(
                status_code=code if code in (500, 502, 503, 504) else 502,
                error_code="AI_PROVIDER_ERROR",
                message="Gemini API server returned an internal error.",
                retry_after_seconds=retry_after,
            )

        raise ApplicationError(
            status_code=502,
            error_code="AI_PROVIDER_ERROR",
            message=f"Gemini API returned an error (HTTP {code}).",
        )

    @staticmethod
    def _retry_after_seconds(exc: errors.APIError) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        value = headers.get("Retry-After") or headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            try:
                target = parsedate_to_datetime(str(value))
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None
