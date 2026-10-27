from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.services.agent_activity_service import list_agent_activities

NOW = datetime(2100, 1, 1, tzinfo=timezone.utc)


def by_id(rows):  # type: ignore[no-untyped-def]
    return {row.agent_id: row for row in rows}


def test_no_fresh_activity_returns_all_idle() -> None:
    with SessionLocal() as db:
        activities = list_agent_activities(db, NOW)
    assert [item.agent_id for item in activities] == ["manager", "developer", "researcher"]
    assert all(item.status == "idle" for item in activities)


def test_running_executions_select_newest_deterministically() -> None:
    with SessionLocal() as db:
        older = Task(title="Older developer activity", status="in_progress", priority="medium", assigned_agent_id="developer")
        newer = Task(title="Newest developer activity", status="in_progress", priority="high", assigned_agent_id="developer")
        research = Task(title="Research activity", status="in_progress", priority="medium", assigned_agent_id="researcher")
        db.add_all([older, newer, research]); db.flush()
        db.add_all([
            TaskExecution(task_id=older.id, agent_id="developer", status="running", input_snapshot="safe", started_at=NOW - timedelta(seconds=2)),
            TaskExecution(task_id=newer.id, agent_id="developer", status="running", input_snapshot="safe", started_at=NOW - timedelta(seconds=1)),
            TaskExecution(task_id=research.id, agent_id="researcher", status="running", input_snapshot="safe", started_at=NOW - timedelta(seconds=1)),
        ]); db.commit(); ids = [older.id, newer.id, research.id]
    try:
        with SessionLocal() as db: activities = by_id(list_agent_activities(db, NOW))
        assert activities["developer"].status == "working"
        assert activities["developer"].current_task_title == "Newest developer activity"
        assert activities["researcher"].status == "working"
        assert activities["manager"].status == "idle"
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.id.in_(ids))); db.commit()


def test_completed_is_idle_failed_is_temporarily_visible_and_stale_running_is_idle() -> None:
    with SessionLocal() as db:
        completed = Task(title="Completed activity", status="done", priority="medium", assigned_agent_id="developer")
        failed = Task(title="Failed activity", status="todo", priority="medium", assigned_agent_id="researcher")
        stale = Task(title="Stale activity", status="in_progress", priority="medium", assigned_agent_id="developer")
        db.add_all([completed, failed, stale]); db.flush()
        db.add_all([
            TaskExecution(task_id=completed.id, agent_id="developer", status="completed", input_snapshot="safe", output_content="done", started_at=NOW - timedelta(seconds=5), completed_at=NOW - timedelta(seconds=4)),
            TaskExecution(task_id=failed.id, agent_id="researcher", status="failed", input_snapshot="safe", error_code="AI_PROVIDER_ERROR", error_message="safe", started_at=NOW - timedelta(seconds=3), completed_at=NOW - timedelta(seconds=2)),
            TaskExecution(task_id=stale.id, agent_id="developer", status="running", input_snapshot="safe", started_at=NOW - timedelta(minutes=11)),
        ]); db.commit(); ids = [completed.id, failed.id, stale.id]
    try:
        with SessionLocal() as db: activities = by_id(list_agent_activities(db, NOW))
        assert activities["developer"].status == "idle"
        assert activities["researcher"].status == "failed"
        assert activities["researcher"].current_task_title == "Failed activity"
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.id.in_(ids))); db.commit()


def test_manager_only_works_during_fresh_finalization_marker() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Activity plan", objective="Test manager activity.", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        run = WorkflowRun(plan_id=plan.id, status="running", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, lease_owner="worker", lease_expires_at=NOW + timedelta(minutes=1), finalizing_at=NOW)
        db.add(run); db.commit(); plan_id = plan.id
    try:
        with SessionLocal() as db: assert by_id(list_agent_activities(db, NOW))["manager"].status == "working"
        with SessionLocal() as db:
            run = db.query(WorkflowRun).filter_by(plan_id=plan_id).one(); run.lease_expires_at = NOW - timedelta(seconds=1); db.commit()
        with SessionLocal() as db: assert by_id(list_agent_activities(db, NOW))["manager"].status == "idle"
    finally:
        with SessionLocal() as db: db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


def test_activity_api_has_public_fields_only() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/agents/activities")
    assert response.status_code == 200
    assert len(response.json()) == 3
    allowed = {"agent_id", "status", "current_task_id", "current_task_title", "workflow_run_id", "activity_type", "updated_at"}
    assert all(set(item) == allowed for item in response.json())
    assert "input_snapshot" not in response.text and "system_instruction" not in response.text
