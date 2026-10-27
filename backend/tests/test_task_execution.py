import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.api.v1.endpoints.task_executions import get_task_execution_service
from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.main import app
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.schemas.ai import AIResponse
from app.services.task_execution_service import TaskExecutionService


class FakeAgentService:
    def __init__(self, *, failure: Exception | None = None, delay: float = 0) -> None:
        self.failure = failure
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.calls.append((agent_id, prompt))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        return AIResponse(provider="mock", model="mock", content=f"Result from {agent_id}")


class SequencedAgentService:
    def __init__(self, outcomes: list[ApplicationError | str]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, ApplicationError):
            raise outcome
        return AIResponse(provider="mock", model="mock", content=outcome)


def create_task(client: TestClient, agent: str | None = "developer", status: str = "todo") -> int:
    response = client.post("/api/v1/tasks", json={"title": "Execution test task", "description": "Produce a safe written result.", "assigned_agent_id": agent, "status": status})
    assert response.status_code == 201
    return response.json()["id"]


def delete_task(task_id: int) -> None:
    with TestClient(app) as client:
        client.delete(f"/api/v1/tasks/{task_id}")


@pytest.mark.parametrize("agent", ["developer", "researcher"])
def test_agent_executes_task_successfully(agent: str) -> None:
    fake = FakeAgentService()
    app.dependency_overrides[get_task_execution_service] = lambda: TaskExecutionService(agent_service=fake)  # type: ignore[arg-type]
    task_id = 0
    try:
        with TestClient(app) as client:
            task_id = create_task(client, agent)
            response = client.post(f"/api/v1/tasks/{task_id}/execute")
            assert response.status_code == 200
            execution = response.json()
            assert execution["status"] == "completed"
            assert execution["output_content"] == f"Result from {agent}"
            assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "done"
            assert fake.calls[0][0] == agent
            assert "system instruction" not in execution["input_snapshot"].lower()
    finally:
        app.dependency_overrides.pop(get_task_execution_service, None)
        if task_id: delete_task(task_id)


@pytest.mark.parametrize("agent,status,code", [
    (None, "todo", "TASK_AGENT_REQUIRED"),
    ("manager", "todo", "TASK_AGENT_NOT_EXECUTABLE"),
    ("developer", "cancelled", "TASK_CANCELLED"),
    ("developer", "done", "TASK_ALREADY_DONE"),
])
def test_invalid_task_states_are_rejected(agent: str | None, status: str, code: str) -> None:
    task_id = 0
    with TestClient(app) as client:
        task_id = create_task(client, agent, status)
        response = client.post(f"/api/v1/tasks/{task_id}/execute")
        assert response.status_code in (409, 422)
        assert response.json()["error"]["code"] == code
    delete_task(task_id)


def test_provider_failure_is_persisted_and_retry_creates_new_execution() -> None:
    failing = FakeAgentService(failure=ApplicationError(502, "AI_PROVIDER_ERROR", "Provider temporarily unavailable."))
    app.dependency_overrides[get_task_execution_service] = lambda: TaskExecutionService(agent_service=failing)  # type: ignore[arg-type]
    task_id = 0
    try:
        with TestClient(app) as client:
            task_id = create_task(client)
            failed = client.post(f"/api/v1/tasks/{task_id}/execute").json()
            assert failed["status"] == "failed" and failed["error_code"] == "AI_PROVIDER_ERROR"
            assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "todo"
            successful = TaskExecutionService(agent_service=FakeAgentService())  # type: ignore[arg-type]
            app.dependency_overrides[get_task_execution_service] = lambda: successful
            completed = client.post(f"/api/v1/tasks/{task_id}/execute").json()
            assert completed["status"] == "completed" and completed["id"] != failed["id"]
            history = client.get(f"/api/v1/tasks/{task_id}/executions").json()
            assert [item["id"] for item in history] == [completed["id"], failed["id"]]
            assert client.get(f"/api/v1/task-executions/{completed['id']}").status_code == 200
    finally:
        app.dependency_overrides.pop(get_task_execution_service, None)
        if task_id: delete_task(task_id)


def test_timeout_is_persisted_without_marking_task_done() -> None:
    service = TaskExecutionService(agent_service=FakeAgentService(delay=.1), timeout_seconds=.01)  # type: ignore[arg-type]
    app.dependency_overrides[get_task_execution_service] = lambda: service
    task_id = 0
    try:
        with TestClient(app) as client:
            task_id = create_task(client)
            execution = client.post(f"/api/v1/tasks/{task_id}/execute").json()
            assert execution["status"] == "failed" and execution["error_code"] == "AI_EXECUTION_TIMEOUT"
            assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "todo"
    finally:
        app.dependency_overrides.pop(get_task_execution_service, None)
        if task_id: delete_task(task_id)


def test_duplicate_running_execution_is_blocked_at_service_and_database_layer() -> None:
    task_id = 0
    with TestClient(app) as client:
        task_id = create_task(client)
    try:
        with SessionLocal() as first_db:
            first, _ = TaskExecutionService(agent_service=FakeAgentService())._start(first_db, task_id)  # type: ignore[arg-type]
        with SessionLocal() as second_db:
            with pytest.raises(ApplicationError) as error:
                TaskExecutionService(agent_service=FakeAgentService())._start(second_db, task_id)  # type: ignore[arg-type]
            assert error.value.error_code == "TASK_ALREADY_RUNNING"
        with SessionLocal() as db:
            TaskExecutionService()._finish(db, first.id, error_code="TEST_CLEANUP", error_message="Test cleanup")
    finally:
        delete_task(task_id)


def test_stale_execution_is_failed_and_recovered_safely() -> None:
    task_id = 0
    with TestClient(app) as client:
        task_id = create_task(client)
    try:
        with SessionLocal() as db:
            task = db.get(Task, task_id)
            assert task is not None
            task.status = "in_progress"
            old = TaskExecution(task_id=task_id, agent_id="developer", status="running", input_snapshot="safe snapshot", started_at=datetime.now(timezone.utc) - timedelta(hours=1))
            db.add(old); db.commit(); old_id = old.id
        service = TaskExecutionService(agent_service=FakeAgentService(), timeout_seconds=1)  # type: ignore[arg-type]
        app.dependency_overrides[get_task_execution_service] = lambda: service
        with TestClient(app) as client:
            recovered = client.post(f"/api/v1/tasks/{task_id}/execute").json()
            assert recovered["status"] == "completed"
            history = client.get(f"/api/v1/tasks/{task_id}/executions").json()
            stale = next(item for item in history if item["id"] == old_id)
            assert stale["status"] == "failed" and stale["error_code"] == "STALE_EXECUTION"
    finally:
        app.dependency_overrides.pop(get_task_execution_service, None)
        delete_task(task_id)


def test_missing_task_and_execution_return_404() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/tasks/999999999/execute").status_code == 404
        assert client.get("/api/v1/tasks/999999999/executions").status_code == 404
        assert client.get("/api/v1/task-executions/999999999").status_code == 404


@pytest.mark.anyio
async def test_transient_503_retries_then_succeeds() -> None:
    agent = SequencedAgentService([ApplicationError(503, "AI_PROVIDER_ERROR", "Unavailable", retry_after_seconds=2), "Recovered output"])
    delays: list[float] = []
    with TestClient(app) as client: task_id = create_task(client)
    try:
        with SessionLocal() as db:
            async def no_sleep(delay: float) -> None:
                assert not db.in_transaction()
                delays.append(delay)
            service = TaskExecutionService(agent_service=agent, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
            execution = await service.execute(db, task_id)
        assert execution.status == "completed" and execution.output_content == "Recovered output"
        assert agent.calls == 2 and delays == [1.0, 1.0]
    finally: delete_task(task_id)


@pytest.mark.anyio
async def test_repeated_503_stops_after_three_calls() -> None:
    errors = [ApplicationError(503, "AI_PROVIDER_ERROR", "Unavailable") for _ in range(3)]
    agent = SequencedAgentService(errors)
    async def no_sleep(_delay: float) -> None: pass
    service = TaskExecutionService(agent_service=agent, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
    with TestClient(app) as client: task_id = create_task(client)
    try:
        with SessionLocal() as db: execution = await service.execute(db, task_id)
        assert execution.status == "failed" and execution.error_code == "AI_PROVIDER_ERROR"
        assert agent.calls == 3
    finally: delete_task(task_id)


@pytest.mark.anyio
@pytest.mark.parametrize(("status", "code"), [(400, "AI_BAD_REQUEST"), (401, "AI_AUTHENTICATION_ERROR"), (403, "AI_AUTHENTICATION_ERROR")])
async def test_non_transient_client_errors_are_not_retried(status: int, code: str) -> None:
    agent = SequencedAgentService([ApplicationError(status, code, "Invalid request")])
    service = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    with TestClient(app) as client: task_id = create_task(client)
    try:
        with SessionLocal() as db: execution = await service.execute(db, task_id)
        assert execution.status == "failed" and execution.error_code == code
        assert agent.calls == 1
    finally: delete_task(task_id)


@pytest.mark.anyio
async def test_cancellation_is_checked_between_retry_attempts() -> None:
    agent = SequencedAgentService([ApplicationError(503, "AI_PROVIDER_ERROR", "Unavailable")])
    async def no_sleep(_delay: float) -> None: pass
    service = TaskExecutionService(agent_service=agent, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
    checks = iter([True, False])
    with TestClient(app) as client: task_id = create_task(client)
    try:
        with SessionLocal() as db:
            with pytest.raises(asyncio.CancelledError):
                await service.execute(db, task_id, keep_alive=lambda: next(checks))
        with SessionLocal() as db:
            execution = db.scalar(select(TaskExecution).where(TaskExecution.task_id == task_id))
            assert execution and execution.status == "cancelled"
    finally: delete_task(task_id)
