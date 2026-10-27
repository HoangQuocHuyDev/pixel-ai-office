from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.api.v1.endpoints.planning import get_planning_service
from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.main import app
from app.models.plan import Plan
from app.models.task import Task
from app.schemas.planning import PlanApproveRequest, PlanProposal
from app.services.planning_service import PlanningService


def proposal_data() -> dict:
    return {
        "title": "Launch reporting dashboard",
        "objective": "Research requirements and implement a reporting dashboard.",
        "tasks": [
            {"title": "Research metrics", "description": "Identify useful reporting metrics.", "priority": "medium", "assigned_agent_id": "researcher", "sequence_order": 1},
            {"title": "Build dashboard", "description": "Implement and test the dashboard.", "priority": "high", "assigned_agent_id": "developer", "sequence_order": 2},
        ],
    }


class MockAIService:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls = 0

    async def generate_structured(self, *_args: object) -> object:
        self.calls += 1
        return self.output


def cleanup_plan(plan_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(Task).where(Task.plan_id == plan_id))
        db.execute(delete(Plan).where(Plan.id == plan_id))
        db.commit()


def test_generate_valid_structured_plan_without_database_write() -> None:
    mock = MockAIService(proposal_data())
    service = PlanningService(ai_service=mock)  # type: ignore[arg-type]
    app.dependency_overrides[get_planning_service] = lambda: service
    try:
        with SessionLocal() as db:
            before = db.scalar(select(func.count()).select_from(Plan))
        with TestClient(app) as client:
            response = client.post("/api/v1/planning/generate", json={"objective": "Create a useful reporting dashboard for operations"})
        assert response.status_code == 200
        assert response.json()["tasks"][0]["assigned_agent_id"] == "researcher"
        assert mock.calls == 1
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Plan)) == before
    finally:
        app.dependency_overrides.pop(get_planning_service, None)


@pytest.mark.anyio
async def test_invalid_ai_output_is_rejected() -> None:
    service = PlanningService(ai_service=MockAIService({"title": "Incomplete"}))  # type: ignore[arg-type]
    with pytest.raises(ApplicationError) as error:
        await service.generate("A sufficiently long objective")
    assert error.value.error_code == "AI_INVALID_STRUCTURED_OUTPUT"


@pytest.mark.parametrize("mutation", [
    lambda p: p["tasks"][0].update(assigned_agent_id="manager"),
    lambda p: p["tasks"].append({**p["tasks"][0], "title": "Duplicate", "sequence_order": 1}),
    lambda p: p.update(tasks=[{**p["tasks"][0], "sequence_order": i + 1} for i in range(11)]),
])
def test_invalid_agent_sequence_and_task_count_rejected(mutation) -> None:  # type: ignore[no-untyped-def]
    payload = proposal_data()
    mutation(payload)
    with TestClient(app) as client:
        response = client.post("/api/v1/planning/approve", json={"proposal": payload, "idempotency_key": uuid4().hex})
    assert response.status_code == 422


def test_approve_is_transactional_idempotent_and_visible_in_plan_and_task_apis() -> None:
    key = uuid4().hex
    body = {"proposal": proposal_data(), "idempotency_key": key}
    plan_id = 0
    with TestClient(app) as client:
        approved = client.post("/api/v1/planning/approve", json=body)
        assert approved.status_code == 201
        plan = approved.json()
        plan_id = plan["id"]
        assert plan["status"] == "approved"
        assert [task["sequence_order"] for task in plan["tasks"]] == [1, 2]
        assert all(task["status"] == "todo" for task in plan["tasks"])
        repeated = client.post("/api/v1/planning/approve", json=body)
        assert repeated.status_code == 201 and repeated.json()["id"] == plan_id
        assert client.post("/api/v1/planning/approve", json={"proposal": {**proposal_data(), "title": "Changed"}, "idempotency_key": key}).status_code == 409
        assert any(item["id"] == plan_id for item in client.get("/api/v1/plans").json())
        assert client.get(f"/api/v1/plans/{plan_id}").json()["tasks"][0]["plan_id"] == plan_id
        linked = client.get(f"/api/v1/tasks?assigned_agent_id=developer").json()
        assert any(task["plan_id"] == plan_id for task in linked)
        assert client.get("/api/v1/agents").status_code == 200
        assert client.get("/api/v1/conversations").status_code == 200
    cleanup_plan(plan_id)


def test_approve_rolls_back_all_records_when_commit_fails() -> None:
    key = uuid4().hex
    payload = PlanApproveRequest.model_validate({"proposal": proposal_data(), "idempotency_key": key})
    with SessionLocal() as db:
        original_commit = db.commit
        db.commit = MagicMock(side_effect=RuntimeError("forced commit failure"))  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            PlanningService().approve(db, payload)
        db.commit = original_commit  # type: ignore[method-assign]
    with SessionLocal() as db:
        assert db.scalar(select(Plan).where(Plan.idempotency_key == key)) is None
        assert db.scalar(select(func.count()).select_from(Task).where(Task.plan_id.in_(select(Plan.id).where(Plan.idempotency_key == key)))) == 0


def test_manual_task_api_remains_available() -> None:
    with TestClient(app) as client:
        created = client.post("/api/v1/tasks", json={"title": "Manual task"})
        assert created.status_code == 201 and created.json()["plan_id"] is None
        client.delete(f"/api/v1/tasks/{created.json()['id']}")
