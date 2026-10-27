from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Pixel AI Office API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "production", "testing"] = "development"
    debug: bool = False
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    database_url: Annotated[SecretStr, Field(min_length=1)]

    # AI Provider Configuration
    ai_provider: Literal["gemini"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_request_timeout_seconds: float = 30.0
    ai_max_output_tokens: int = 2048

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_release_debug_value(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() == "release":
            return False
        return value

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
