from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.main import app
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.ai import AIResponse
from app.schemas.planning import PlanApproveRequest
from app.services.planning_service import PlanningService
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import WorkflowOrchestrator, cancel_workflow


class FakeAgentService:
    def __init__(self, fail_agent: str | None = None, manager_failures: int = 0) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_agent = fail_agent
        self.manager_failures = manager_failures

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.calls.append((agent_id, prompt))
        if agent_id == self.fail_agent:
            raise RuntimeError("mock provider failure")
        if agent_id == "manager" and self.manager_failures:
            self.manager_failures -= 1
            raise ApplicationError(503, "AI_PROVIDER_ERROR", "mock finalization failure")
        return AIResponse(provider="mock", model="mock", content=f"Output from {agent_id}: safe result")


class TransientAgentService(FakeAgentService):
    def __init__(self) -> None:
        super().__init__()
        self.transient_failures = 1

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.calls.append((agent_id, prompt))
        if agent_id == "researcher" and self.transient_failures:
            self.transient_failures -= 1
            raise ApplicationError(503, "AI_PROVIDER_ERROR", "Temporarily unavailable.")
        return AIResponse(provider="mock", model="mock", content=f"Output from {agent_id}: safe result")


def create_plan() -> int:
    payload = PlanApproveRequest.model_validate({
        "idempotency_key": uuid4().hex,
        "proposal": {"title": "Workflow test plan", "objective": "Validate durable sequential orchestration.", "tasks": [
            {"title": "Research first", "description": "Collect relevant facts.", "priority": "medium", "assigned_agent_id": "researcher", "sequence_order": 1},
            {"title": "Develop second", "description": "Use the research result.", "priority": "high", "assigned_agent_id": "developer", "sequence_order": 2},
        ]},
    })
    with SessionLocal() as db:
        return PlanningService().approve(db, payload).id


def cleanup_plan(plan_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(Task).where(Task.plan_id == plan_id))
        db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


def orchestrator(fake: FakeAgentService, **kwargs) -> WorkflowOrchestrator:  # type: ignore[no-untyped-def]
    execution = TaskExecutionService(agent_service=fake, timeout_seconds=2)  # type: ignore[arg-type]
    return WorkflowOrchestrator(execution_service=execution, agent_service=fake, **kwargs)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_workflow_runs_in_sequence_transfers_context_and_creates_manager_report() -> None:
    plan_id = create_plan(); fake = FakeAgentService(); service = orchestrator(fake)
    try:
        with SessionLocal() as db:
            run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db:
            claimed = service.claim_next(db, "worker-a")
            assert claimed and claimed.id == run.id
        result = await service.process(run.id, "worker-a")
        assert result.status == "completed" and result.final_report
        assert [call[0] for call in fake.calls] == ["researcher", "developer", "manager"]
        assert "untrusted reference data" in fake.calls[1][1]
        assert "Output from researcher" in fake.calls[1][1]
        with SessionLocal() as db:
            tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
            assert all(task.status == "done" for task in tasks)
    finally: cleanup_plan(plan_id)


def test_start_is_idempotent_and_duplicate_active_run_is_rejected() -> None:
    plan_id = create_plan(); service = WorkflowOrchestrator(); key = uuid4().hex
    try:
        with SessionLocal() as db: first = service.start_workflow(db, plan_id, key)
        with SessionLocal() as db: assert service.start_workflow(db, plan_id, key).id == first.id
        with SessionLocal() as db:
            with pytest.raises(Exception) as error: service.start_workflow(db, plan_id, uuid4().hex)
            assert getattr(error.value, "error_code", None) == "WORKFLOW_ALREADY_ACTIVE"
    finally: cleanup_plan(plan_id)


def test_draft_cancelled_and_empty_plans_are_rejected() -> None:
    service = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan = Plan(title="Empty workflow plan", objective="Validate workflow preconditions.", status="draft", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.commit(); plan_id = plan.id
    try:
        for plan_status, expected in (("draft", "PLAN_NOT_APPROVED"), ("cancelled", "PLAN_NOT_APPROVED"), ("approved", "PLAN_HAS_NO_TASKS")):
            with SessionLocal() as db:
                plan = db.get(Plan, plan_id); assert plan
                plan.status = plan_status; db.commit()
            with SessionLocal() as db:
                with pytest.raises(Exception) as error: service.start_workflow(db, plan_id, uuid4().hex)
                assert getattr(error.value, "error_code", None) == expected
    finally: cleanup_plan(plan_id)


@pytest.mark.anyio
async def test_failed_task_stops_workflow_and_does_not_run_next_task() -> None:
    plan_id = create_plan(); fake = FakeAgentService(fail_agent="researcher"); service = orchestrator(fake)
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: service.claim_next(db, "worker-fail")
        result = await service.process(run.id, "worker-fail")
        assert result.status == "failed"
        assert [agent for agent, _ in fake.calls] == ["researcher"]
        with SessionLocal() as db:
            tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
            assert tasks[0].status == "todo" and tasks[1].status == "todo"
    finally: cleanup_plan(plan_id)


@pytest.mark.anyio
async def test_recovery_skips_completed_task() -> None:
    plan_id = create_plan(); fake = FakeAgentService(); service = orchestrator(fake)
    try:
        with SessionLocal() as db:
            first = db.scalar(select(Task).where(Task.plan_id == plan_id, Task.sequence_order == 1))
            assert first is not None
            first.status = "done"; first.completed_at = datetime.now(timezone.utc)
            db.add(TaskExecution(task_id=first.id, agent_id="researcher", status="completed", input_snapshot="safe", output_content="Recovered prior result", completed_at=datetime.now(timezone.utc)))
            db.commit()
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: service.claim_next(db, "worker-recovery")
        result = await service.process(run.id, "worker-recovery")
        assert result.status == "completed"
        assert [agent for agent, _ in fake.calls] == ["developer", "manager"]
        assert "Recovered prior result" in fake.calls[0][1]
    finally: cleanup_plan(plan_id)


def test_worker_claim_is_exclusive_and_stale_lease_is_recovered() -> None:
    plan_id = create_plan(); service = WorkflowOrchestrator(lease_seconds=1)
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: assert service.claim_next(db, "worker-one") is not None
        with SessionLocal() as db: assert service.claim_next(db, "worker-two") is None
        with SessionLocal() as db:
            stored = db.get(WorkflowRun, run.id); assert stored
            stored.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
        with SessionLocal() as db:
            recovered = service.claim_next(db, "worker-two")
            assert recovered and recovered.id == run.id and recovered.attempt_count == 2
    finally: cleanup_plan(plan_id)


def test_cancel_workflow_is_persisted_and_terminal() -> None:
    plan_id = create_plan(); service = WorkflowOrchestrator()
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db:
            cancelled = cancel_workflow(db, run.id)
            assert cancelled.status == "cancelled" and cancelled.error_code == "WORKFLOW_CANCELLED"
        with SessionLocal() as db: assert cancel_workflow(db, run.id).status == "cancelled"
    finally: cleanup_plan(plan_id)


@pytest.mark.anyio
async def test_final_report_transient_failure_retries_without_losing_task_results() -> None:
    plan_id = create_plan(); fake = FakeAgentService(manager_failures=1)
    async def no_sleep(_delay: float) -> None: pass
    execution = TaskExecutionService(agent_service=fake, timeout_seconds=2, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
    service = WorkflowOrchestrator(execution_service=execution, agent_service=fake)  # type: ignore[arg-type]
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: service.claim_next(db, "worker-final")
        result = await service.process(run.id, "worker-final")
        assert result.status == "completed" and result.final_report
        assert [agent for agent, _ in fake.calls].count("developer") == 1
        assert [agent for agent, _ in fake.calls].count("researcher") == 1
        assert [agent for agent, _ in fake.calls].count("manager") == 2
    finally: cleanup_plan(plan_id)


@pytest.mark.anyio
async def test_final_report_stops_after_three_transient_failures() -> None:
    plan_id = create_plan(); fake = FakeAgentService(manager_failures=3)
    async def no_sleep(_delay: float) -> None: pass
    execution = TaskExecutionService(agent_service=fake, timeout_seconds=2, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
    service = WorkflowOrchestrator(execution_service=execution, agent_service=fake)  # type: ignore[arg-type]
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: service.claim_next(db, "worker-final-fail")
        result = await service.process(run.id, "worker-final-fail")
        assert result.status == "failed" and result.error_code == "FINAL_REPORT_FAILED"
        assert [agent for agent, _ in fake.calls].count("manager") == 3
        with SessionLocal() as db:
            assert all(task.status == "done" for task in db.scalars(select(Task).where(Task.plan_id == plan_id)).all())
    finally: cleanup_plan(plan_id)


def test_workflow_api_start_status_history_and_cancel() -> None:
    plan_id = create_plan()
    try:
        with TestClient(app) as client:
            start = client.post(f"/api/v1/plans/{plan_id}/workflows", json={"idempotency_key": uuid4().hex})
            assert start.status_code == 202 and start.json()["status"] == "pending"
            run_id = start.json()["id"]
            assert client.get(f"/api/v1/workflows/{run_id}").status_code == 200
            assert client.get(f"/api/v1/plans/{plan_id}/workflows").json()[0]["id"] == run_id
            assert client.post(f"/api/v1/workflows/{run_id}/cancel").json()["status"] == "cancelled"
    finally: cleanup_plan(plan_id)


@pytest.mark.anyio
async def test_transient_retry_renews_workflow_lease() -> None:
    plan_id = create_plan(); fake = TransientAgentService()
    async def no_sleep(_delay: float) -> None: pass
    execution = TaskExecutionService(agent_service=fake, timeout_seconds=2, sleep=no_sleep, jitter=lambda _a, _b: 0)  # type: ignore[arg-type]
    service = WorkflowOrchestrator(execution_service=execution, agent_service=fake, lease_seconds=120)  # type: ignore[arg-type]
    renewals = 0
    original = service._renew_lease
    def tracked(run_id: int, worker_id: str) -> bool:
        nonlocal renewals
        renewals += 1
        return original(run_id, worker_id)
    service._renew_lease = tracked  # type: ignore[method-assign]
    try:
        with SessionLocal() as db: run = service.start_workflow(db, plan_id, uuid4().hex)
        with SessionLocal() as db: service.claim_next(db, "worker-retry-heartbeat")
        result = await service.process(run.id, "worker-retry-heartbeat")
        assert result.status == "completed"
        assert [agent for agent, _ in fake.calls] == ["researcher", "researcher", "developer", "manager"]
        assert renewals >= 4
    finally: cleanup_plan(plan_id)
