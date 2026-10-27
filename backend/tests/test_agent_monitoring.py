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
from app.services.agent_monitoring_service import get_agent_monitoring, get_agent_timeline, get_monitoring_summary


def test_monitoring_summary_and_unknown_agent() -> None:
    with SessionLocal() as db:
        summary = get_monitoring_summary(db)
    assert summary.total_agents == 3
    assert summary.working_agents + summary.idle_agents + summary.failed_agents == 3
    with TestClient(app) as client:
        response = client.get("/api/v1/agents/unknown/monitoring")
    assert response.status_code == 404


def test_monitoring_statistics_timeline_pagination_and_public_fields() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        baseline = get_agent_monitoring(db, "developer").statistics
        baseline_timeline_total = get_agent_timeline(db, "developer", 1, 0).total
    with SessionLocal() as db:
        plan = Plan(title="Monitoring plan", objective="Verify monitoring", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        task = Task(title="Monitored task", status="done", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1, completed_at=now)
        db.add(task); db.flush()
        completed = TaskExecution(task_id=task.id, agent_id="developer", status="completed", input_snapshot="SECRET INPUT", output_content="Safe result", started_at=now - timedelta(seconds=10), completed_at=now)
        failed = TaskExecution(task_id=task.id, agent_id="developer", status="failed", input_snapshot="SECRET INPUT 2", error_code="SAFE_ERROR", error_message="Safe failure", started_at=now - timedelta(seconds=30), completed_at=now - timedelta(seconds=20))
        db.add_all([completed, failed]); db.flush(); execution_ids = {completed.id, failed.id}
        workflow = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, started_at=now - timedelta(seconds=40), completed_at=now, final_report="Report")
        db.add(workflow); db.commit(); plan_id = plan.id
    try:
        with SessionLocal() as db:
            monitoring = get_agent_monitoring(db, "developer")
            timeline = get_agent_timeline(db, "developer", 2, 0)
            second_page = get_agent_timeline(db, "developer", 2, 2)
            manager_timeline = get_agent_timeline(db, "manager", 20, 0)
        assert monitoring.agent.name == "Developer AI"
        assert monitoring.statistics.total_executions == baseline.total_executions + 2
        assert monitoring.statistics.completed_executions == baseline.completed_executions + 1
        assert monitoring.statistics.failed_executions == baseline.failed_executions + 1
        finished = monitoring.statistics.completed_executions + monitoring.statistics.failed_executions + monitoring.statistics.cancelled_executions
        assert monitoring.statistics.success_rate == round(monitoring.statistics.completed_executions * 100 / finished, 1)
        own_executions = [item for item in monitoring.recent_executions if item.id in execution_ids]
        assert {item.duration_seconds for item in own_executions} == {10.0}
        assert any(item.output_content == "Safe result" for item in own_executions)
        assert timeline.total == baseline_timeline_total + 4 and len(timeline.items) == 2 and len(second_page.items) == 2
        ids = [item.event_id for item in timeline.items + second_page.items]
        assert len(ids) == len(set(ids))
        assert [item.timestamp for item in timeline.items] == sorted((item.timestamp for item in timeline.items), reverse=True)
        assert any(item.event_type == "manager_final_report_completed" for item in manager_timeline.items)
        with TestClient(app) as client:
            response = client.get("/api/v1/agents/developer/monitoring")
            summary = client.get("/api/v1/agents/monitoring/summary")
        assert response.status_code == 200 and summary.status_code == 200
        assert "SECRET INPUT" not in response.text
        assert response.json()["current_activity"]["agent_id"] == "developer"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()
