from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.main import app
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.services.artifact_service import backfill_artifacts, create_execution_artifact, create_workflow_artifact
from app.services.task_execution_service import TaskExecutionService


def test_completed_execution_creates_one_artifact_and_failures_do_not() -> None:
    with SessionLocal() as db:
        task = Task(title="Artifact task", status="in_progress", priority="medium", assigned_agent_id="developer")
        db.add(task); db.flush()
        execution = TaskExecution(task_id=task.id, agent_id="developer", status="running", input_snapshot="private prompt")
        failed = TaskExecution(task_id=task.id, agent_id="developer", status="failed", input_snapshot="private", error_message="failed", completed_at=datetime.now(timezone.utc))
        db.add_all([execution, failed]); db.commit(); task_id = task.id; execution_id = execution.id; failed_id = failed.id
    try:
        with SessionLocal() as db:
            result = TaskExecutionService()._finish(db, execution_id, output="```python\nprint('safe')\n```")
            assert result.status == "completed"
            artifacts = list(db.scalars(select(Artifact).where(Artifact.task_id == task_id)))
            assert len(artifacts) == 1 and artifacts[0].artifact_type == "code"
            failed_execution = db.get(TaskExecution, failed_id); task = db.get(Task, task_id)
            assert failed_execution is not None and task is not None
            assert create_execution_artifact(db, failed_execution, task) is None
            assert create_execution_artifact(db, result, task).id == artifacts[0].id
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.id == task_id)); db.commit()


def test_report_artifact_and_backfill_are_idempotent() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        plan = Plan(title="Artifacts / unsafe .. plan", objective="test", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        task = Task(title="Research output", status="done", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1, completed_at=now)
        db.add(task); db.flush()
        execution = TaskExecution(task_id=task.id, agent_id="researcher", status="completed", input_snapshot="secret system prompt", output_content="Research findings", started_at=now - timedelta(seconds=4), completed_at=now)
        workflow = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, final_report="# Final report", completed_at=now)
        db.add_all([execution, workflow]); db.commit(); plan_id = plan.id; execution_id = execution.id; workflow_id = workflow.id
    try:
        with SessionLocal() as db:
            assert backfill_artifacts(db, execution_ids={execution_id}, workflow_ids={workflow_id}) == (1, 1)
            assert backfill_artifacts(db, execution_ids={execution_id}, workflow_ids={workflow_id}) == (0, 0)
            execution_artifact = db.scalar(select(Artifact).where(Artifact.task_execution_id == execution_id))
            report = db.scalar(select(Artifact).where(Artifact.workflow_run_id == workflow_id))
            assert execution_artifact and execution_artifact.artifact_type == "research"
            assert report and report.artifact_type == "report" and report.agent_id == "manager"
            assert create_workflow_artifact(db, db.get(WorkflowRun, workflow_id), db.get(Plan, plan_id)).id == report.id  # type: ignore[arg-type]
            db.commit()
        with TestClient(app) as client:
            listing = client.get("/api/v1/artifacts", params={"search": "Artifacts", "agent_id": "manager", "limit": 1})
            detail = client.get(f"/api/v1/artifacts/{report.id}")
            summary = client.get("/api/v1/artifacts/summary")
            download = client.get(f"/api/v1/artifacts/{report.id}/download")
        assert listing.status_code == 200 and listing.json()["total"] >= 1
        assert "content" not in listing.json()["items"][0]
        assert detail.json()["content"] == "# Final report"
        assert summary.status_code == 200 and summary.json()["reports"] >= 1
        assert download.headers["content-disposition"].startswith(f'attachment; filename="artifact-{report.id}-')
        assert ".." not in download.headers["content-disposition"] and "/" not in download.headers["content-disposition"]
        assert "secret system prompt" not in listing.text + detail.text
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id)); db.execute(delete(Plan).where(Plan.id == plan_id)); db.commit()


def test_artifact_constraints_and_completion_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as db:
        orphan = Artifact(title="orphan", artifact_type="document", content="text", content_format="plain_text")
        db.add(orphan)
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        task = Task(title="Rollback artifact", status="in_progress", priority="medium", assigned_agent_id="developer")
        db.add(task); db.flush()
        execution = TaskExecution(task_id=task.id, agent_id="developer", status="running", input_snapshot="safe")
        db.add(execution); db.commit(); task_id = task.id; execution_id = execution.id
    try:
        def fail_creation(*args: object, **kwargs: object) -> None: raise RuntimeError("simulated artifact failure")
        monkeypatch.setattr("app.services.task_execution_service.create_execution_artifact", fail_creation)
        with SessionLocal() as db, pytest.raises(RuntimeError): TaskExecutionService()._finish(db, execution_id, output="result")
        with SessionLocal() as db:
            assert db.get(TaskExecution, execution_id).status == "running"  # type: ignore[union-attr]
            assert db.scalar(select(Artifact).where(Artifact.task_execution_id == execution_id)) is None
    finally:
        with SessionLocal() as db: db.execute(delete(Task).where(Task.id == task_id)); db.commit()
