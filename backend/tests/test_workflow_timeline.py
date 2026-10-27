from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.services.artifact_service import create_execution_artifact, create_workflow_artifact
from app.services.workflow_timeline_service import get_workflow_timeline

NOW = datetime.now(timezone.utc)


def test_timeline_order_progress_attempts_and_artifacts() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Timeline plan", objective="Visualize real execution", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        tasks = [
            Task(title="Completed", status="done", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1, completed_at=NOW - timedelta(seconds=20)),
            Task(title="Failed", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=2),
            Task(title="Cancelled", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=3),
            Task(title="Running", status="in_progress", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=4),
            Task(title="Pending", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=5),
        ]
        db.add_all(tasks); db.flush()
        run = WorkflowRun(plan_id=plan.id, status="running", total_tasks=5, completed_tasks=1, current_task_id=tasks[3].id, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=2), lease_owner="worker", lease_expires_at=NOW + timedelta(minutes=1))
        db.add(run); db.flush()
        executions = [
            TaskExecution(task_id=tasks[0].id, workflow_run_id=run.id, agent_id="developer", status="completed", input_snapshot="secret context", output_content="completed result", started_at=NOW - timedelta(seconds=30), completed_at=NOW - timedelta(seconds=20)),
            TaskExecution(task_id=tasks[1].id, workflow_run_id=run.id, agent_id="researcher", status="failed", input_snapshot="private", error_code="SAFE", error_message="Safe failure", started_at=NOW - timedelta(seconds=18), completed_at=NOW - timedelta(seconds=15)),
            TaskExecution(task_id=tasks[2].id, workflow_run_id=run.id, agent_id="developer", status="cancelled", input_snapshot="private", error_code="CANCELLED", error_message="Cancelled", started_at=NOW - timedelta(seconds=14), completed_at=NOW - timedelta(seconds=12)),
            TaskExecution(task_id=tasks[3].id, workflow_run_id=run.id, agent_id="researcher", status="running", input_snapshot="private", started_at=NOW - timedelta(seconds=10)),
        ]
        db.add_all(executions); db.flush(); artifact = create_execution_artifact(db, executions[0], tasks[0]); db.commit(); plan_id = plan.id; run_id = run.id
    try:
        with SessionLocal() as db: timeline = get_workflow_timeline(db, run_id)
        assert [step.task_title for step in timeline.steps] == ["Completed", "Failed", "Cancelled", "Running", "Pending"]
        assert [step.status for step in timeline.steps] == ["completed", "failed", "cancelled", "running", "pending"]
        assert timeline.progress.completed_tasks == 1 and timeline.progress.progress_percentage == 20.0
        assert timeline.progress.failed_tasks == timeline.progress.cancelled_tasks == timeline.progress.running_tasks == timeline.progress.pending_tasks == 1
        assert timeline.steps[0].attempts[0].result_preview == "completed result"
        assert timeline.steps[0].attempts[0].artifacts[0].id == artifact.id
        assert "secret context" not in timeline.model_dump_json()
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.plan_id == plan_id)); db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


def test_finalization_report_and_multiple_run_time_windows_are_isolated() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Run isolation", objective="Separate attempts", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        task = Task(title="Shared task", status="done", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1, completed_at=NOW)
        db.add(task); db.flush()
        first = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=10), completed_at=NOW - timedelta(minutes=8), final_report="First report")
        second = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=5), completed_at=NOW - timedelta(minutes=3), final_report="Second report")
        db.add_all([first, second]); db.flush()
        db.add_all([
            TaskExecution(task_id=task.id, workflow_run_id=first.id, agent_id="developer", status="completed", input_snapshot="one", output_content="first", started_at=NOW - timedelta(minutes=9), completed_at=NOW - timedelta(minutes=8, seconds=30)),
            TaskExecution(task_id=task.id, workflow_run_id=second.id, agent_id="developer", status="completed", input_snapshot="two", output_content="second", started_at=NOW - timedelta(minutes=4), completed_at=NOW - timedelta(minutes=3, seconds=30)),
        ])
        report = create_workflow_artifact(db, second, plan); db.commit(); plan_id = plan.id; first_id = first.id; second_id = second.id
    try:
        with SessionLocal() as db:
            first_timeline = get_workflow_timeline(db, first_id); second_timeline = get_workflow_timeline(db, second_id)
        assert [attempt.result_preview for attempt in first_timeline.steps[0].attempts] == ["first"]
        assert [attempt.result_preview for attempt in second_timeline.steps[0].attempts] == ["second"]
        assert second_timeline.finalization.status == "completed"
        assert second_timeline.finalization.report_preview == "Second report"
        assert second_timeline.finalization.artifacts[0].id == report.id
        assert first_timeline.finalization.artifacts == []
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.plan_id == plan_id)); db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


def test_timeline_api_missing_workflow_and_public_contract() -> None:
    with TestClient(app) as client:
        missing = client.get("/api/v1/workflows/999999999/timeline")
    assert missing.status_code == 404
    assert "database_url" not in missing.text and "system_instruction" not in missing.text


def test_manual_and_legacy_executions_excluded_from_workflow_timeline() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Integrity plan", objective="Check manual exclusion", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        task1 = Task(title="Pre-existing task", status="done", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1, completed_at=NOW - timedelta(minutes=15))
        task2 = Task(title="Manual failed task", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=2)
        db.add_all([task1, task2]); db.flush()
        run = WorkflowRun(plan_id=plan.id, status="running", total_tasks=2, completed_tasks=1, current_task_id=task2.id, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=5))
        db.add(run); db.flush()
        legacy_exec = TaskExecution(task_id=task1.id, workflow_run_id=None, agent_id="developer", status="completed", input_snapshot="legacy", output_content="legacy result", started_at=NOW - timedelta(minutes=16), completed_at=NOW - timedelta(minutes=15))
        manual_exec = TaskExecution(task_id=task2.id, workflow_run_id=None, agent_id="researcher", status="failed", input_snapshot="manual", error_code="MANUAL_ERR", error_message="Manual error", started_at=NOW - timedelta(minutes=2), completed_at=NOW - timedelta(minutes=1))
        db.add_all([legacy_exec, manual_exec]); db.commit()
        plan_id = plan.id; run_id = run.id
    try:
        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run_id)
        assert timeline.steps[0].attempts == []
        assert timeline.steps[0].pre_existing is True
        assert timeline.steps[0].status == "completed"
        assert timeline.steps[1].attempts == []
        assert timeline.steps[1].pre_existing is False
        assert timeline.steps[1].status == "pending"
        assert timeline.execution_scope_note == "Task executions are linked directly to this workflow run via verified workflow_run_id foreign keys."
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.plan_id == plan_id)); db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


class _MockAgentService:
    async def generate_response(self, agent_id: str, prompt: str):
        from app.schemas.ai import AIResponse
        return AIResponse(provider="mock", model="mock", content=f"Output for {agent_id}")


@pytest.mark.anyio
async def test_task_execution_service_validates_workflow_ownership_and_plan_integrity() -> None:
    import pytest
    from app.core.exceptions import ApplicationError
    from app.services.task_execution_service import TaskExecutionService

    service = TaskExecutionService(agent_service=_MockAgentService())  # type: ignore[arg-type]
    with SessionLocal() as db:
        plan_a = Plan(title="Plan A", objective="Obj A", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        plan_b = Plan(title="Plan B", objective="Obj B", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add_all([plan_a, plan_b]); db.flush()
        task_a = Task(title="Task A", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan_a.id, sequence_order=1)
        task_b = Task(title="Task B", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan_b.id, sequence_order=1)
        db.add_all([task_a, task_b]); db.flush()
        run_a = WorkflowRun(plan_id=plan_a.id, status="running", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run_a); db.commit()
        plan_a_id = plan_a.id; plan_b_id = plan_b.id; task_a_id = task_a.id; task_b_id = task_b.id; run_a_id = run_a.id
    try:
        with SessionLocal() as db:
            with pytest.raises(ApplicationError) as exc_missing:
                await service.execute(db, task_a_id, workflow_run_id=999999999)
            assert exc_missing.value.status_code == 404
            assert exc_missing.value.error_code == "WORKFLOW_NOT_FOUND"

            with pytest.raises(ApplicationError) as exc_mismatch:
                await service.execute(db, task_b_id, workflow_run_id=run_a_id)
            assert exc_mismatch.value.status_code == 422
            assert exc_mismatch.value.error_code == "WORKFLOW_PLAN_MISMATCH"

            exec_workflow = await service.execute(db, task_a_id, workflow_run_id=run_a_id)
            assert exec_workflow.status == "completed"
            assert exec_workflow.workflow_run_id == run_a_id

            task_a2 = Task(title="Task A2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan_a_id, sequence_order=2)
            db.add(task_a2); db.commit(); db.refresh(task_a2)
            exec_manual = await service.execute(db, task_a2.id)
            assert exec_manual.status == "completed"
            assert exec_manual.workflow_run_id is None
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id.in_([plan_a_id, plan_b_id])))
            db.execute(delete(Plan).where(Plan.id.in_([plan_a_id, plan_b_id])))
            db.commit()


@pytest.mark.anyio
async def test_workflow_orchestrator_links_execution_to_run_id() -> None:
    from app.services.task_execution_service import TaskExecutionService
    from app.services.workflow_orchestrator import WorkflowOrchestrator

    agent = _MockAgentService()
    exec_service = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orchestrator = WorkflowOrchestrator(execution_service=exec_service, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan = Plan(title="Auto plan", objective="Orchestrator trace", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        task = Task(title="Orchestrated task", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1)
        db.add(task); db.flush()
        run = orchestrator.start_workflow(db, plan.id, uuid4().hex)
        plan_id = plan.id; run_id = run.id; task_id = task.id

    try:
        with SessionLocal() as db:
            claimed = orchestrator.claim_next(db, "test-worker")
            assert claimed is not None and claimed.id == run_id
        completed_run = await orchestrator.process(run_id, "test-worker")
        assert completed_run.status == "completed"

        with SessionLocal() as db:
            execution = db.scalar(select(TaskExecution).where(TaskExecution.task_id == task_id))
            assert execution is not None
            assert execution.workflow_run_id == run_id

            timeline = get_workflow_timeline(db, run_id)
            assert len(timeline.steps[0].attempts) == 1
            assert timeline.steps[0].attempts[0].id == execution.id
            assert timeline.steps[0].status == "completed"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()
