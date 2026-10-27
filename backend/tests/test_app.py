import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import ApplicationError
from app.core.logging import (
    HANDLER_MARKER,
    LOG_FORMAT,
    SensitiveDataFormatter,
    configure_logging,
)
from app.core.config import Settings
from app.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "pixel-ai-office-api",
        "version": "0.1.0",
    }


def create_error_test_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/application-error")
    def application_error() -> None:
        raise ApplicationError(409, "RESOURCE_CONFLICT", "Resource conflict.")

    @test_app.get("/http-error")
    def http_error() -> None:
        raise HTTPException(status_code=404, detail="Resource not found.")

    @test_app.get("/validation/{item_id}")
    def validation_error(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @test_app.get("/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError("database_password=never-return-this")

    return test_app


def test_application_error_handler() -> None:
    with TestClient(create_error_test_app()) as client:
        response = client.get("/application-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "RESOURCE_CONFLICT",
            "message": "Resource conflict.",
        }
    }


def test_http_exception_handler() -> None:
    with TestClient(create_error_test_app()) as client:
        response = client.get("/http-error")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "HTTP_ERROR", "message": "Resource not found."}
    }


def test_validation_exception_handler_returns_safe_details() -> None:
    with TestClient(create_error_test_app()) as client:
        response = client.get("/validation/not-an-integer")

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["details"][0]["location"] == ["path", "item_id"]
    assert "input" not in body["error"]["details"][0]


def test_unexpected_exception_returns_safe_response() -> None:
    with TestClient(
        create_error_test_app(), raise_server_exceptions=False
    ) as client:
        response = client.get("/unexpected-error")

    response_text = response.text.lower()
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
        }
    }
    assert "traceback" not in response_text
    assert "runtimeerror" not in response_text
    assert "password" not in response_text


def test_logging_configuration_does_not_duplicate_handlers() -> None:
    configure_logging("INFO")
    configure_logging("DEBUG")

    application_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, HANDLER_MARKER, False)
    ]
    assert len(application_handlers) == 1
    assert application_handlers[0].level == logging.DEBUG


def test_logging_formatter_redacts_sensitive_values() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Request failed with password=private-value",
        args=(),
        exc_info=None,
    )

    output = SensitiveDataFormatter(LOG_FORMAT).format(record)

    assert "private-value" not in output
    assert "password=[REDACTED]" in output


def test_release_environment_disables_debug_mode() -> None:
    settings = Settings(
        debug="release",  # type: ignore[arg-type]
        database_url="postgresql+psycopg://user:password@localhost/database",
        _env_file=None,
    )

    assert settings.debug is False
