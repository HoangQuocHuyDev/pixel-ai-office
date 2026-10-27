import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.logging import LOG_FORMAT, SensitiveDataFormatter
from app.main import MAX_REQUEST_BYTES, app


def test_cors_allows_only_local_frontend_without_credentials() -> None:
    with TestClient(app) as client:
        allowed = client.options("/api/v1/system/status", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        rejected = client.options("/api/v1/system/status", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in rejected.headers


def test_system_status_is_safe_and_does_not_call_gemini(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Gemini must not be called by status")
    monkeypatch.setattr("app.ai.factory.get_ai_provider", forbidden)
    with TestClient(app) as client: response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["backend_status"] == "ok" and body["database_status"] == "connected"
    assert body["application_mode"] == "local-first" and body["agents_count"] == 3
    serialized = response.text.lower()
    for forbidden_value in ("database_url", "postgresql", "password", "gemini_api_key", "system_instruction"):
        assert forbidden_value not in serialized


def test_api_key_label_is_redacted_from_logs() -> None:
    record = logging.LogRecord("security", logging.ERROR, __file__, 1, "GEMINI_API_KEY=super-secret-value", (), None)
    output = SensitiveDataFormatter(LOG_FORMAT).format(record)
    assert "super-secret-value" not in output and "[REDACTED]" in output


def test_oversized_request_is_rejected_before_validation() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/tasks", content=b"x", headers={"Content-Length": str(MAX_REQUEST_BYTES + 1), "Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_pagination_limit_remains_enforced() -> None:
    with TestClient(app) as client: response = client.get("/api/v1/artifacts", params={"limit": 101})
    assert response.status_code == 422


def test_local_startup_script_binds_loopback_only() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "run_local.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in source
    assert 'host="0.0.0.0"' not in source
