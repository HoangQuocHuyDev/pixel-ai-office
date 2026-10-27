from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.main import app
from app.models.agent_handoff import AgentHandoff
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.ai import AIResponse
from app.services.artifact_service import create_execution_artifact
from app.services.handoff_service import (
    create_agent_handoff,
    extract_handoff_content,
    format_handoff_for_context,
)
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import WorkflowOrchestrator
from app.services.workflow_timeline_service import get_workflow_timeline

NOW = datetime.now(timezone.utc)


class _MockAgentService:
    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        content = self.responses.get(
            agent_id,
            f"Output from {agent_id}.\n- Finding 1: Important detail\n- Finding 2: Crucial fact\nDeliverables:\n- Architecture schema\nNext steps:\nProceed with implementation.",
        )
        return AIResponse(provider="mock", model="mock", content=content)


def test_extract_handoff_content_deterministic() -> None:
    raw_output = (
        "This is the executive summary of the research completed for the module.\n\n"
        "Key Findings:\n"
        "- Discovered high-performance caching strategy with Redis\n"
        "- Database queries should use indexed compound keys\n\n"
        "Deliverables:\n"
        "- Schema definition artifact\n\n"
        "Next Steps:\n"
        "Implement repository methods and update migration scripts."
    )
    src_task = Task(title="Research Caching", assigned_agent_id="researcher")
    tgt_task = Task(title="Implement Repository", assigned_agent_id="developer", description="Build repository pattern")
    result = extract_handoff_content(
        output_content=raw_output,
        source_task=src_task,
        target_task=tgt_task,
        artifacts=[],
    )
    assert "executive summary" in result["summary"]
    assert len(result["key_findings"]) >= 2
    assert any("Redis" in f for f in result["key_findings"])
    assert any("Research Caching" in d for d in result["deliverables"])
    assert "Implement Repository" in (result["next_steps"] or "")


def test_format_handoff_for_context() -> None:
    handoff = AgentHandoff(
        workflow_run_id=1,
        source_task_execution_id=10,
        source_agent_id="researcher",
        target_task_id=20,
        target_agent_id="developer",
        summary="Research completed successfully with benchmark results.",
        key_findings=["Postgres JSONB supports indexed queries", "Write performance meets SLA"],
        deliverables=["Benchmark script", "Data model proposal"],
        next_steps="Develop the migration and repository.",
        artifact_ids=[],
    )
    formatted = format_handoff_for_context(handoff, source_task_title="Research Module")
    assert "Structured Handoff from Researcher AI to Developer AI" in formatted
    assert "Summary: Research completed successfully" in formatted
    assert "• Postgres JSONB supports indexed queries" in formatted
    assert "• Benchmark script" in formatted
    assert "Next steps for this task: Develop the migration and repository." in formatted


def test_handoff_creation_and_idempotency() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Handoff Plan", objective="Test handoff DB persistence", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="done", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.flush()
        run = WorkflowRun(plan_id=plan.id, status="running", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run); db.flush()
        execution = TaskExecution(task_id=t1.id, workflow_run_id=run.id, agent_id="researcher", status="completed", input_snapshot="input", output_content="Analysis completed.\n- Point A\n- Point B\nDeliverables:\n- Report", started_at=NOW)
        db.add(execution); db.flush()
        artifact = create_execution_artifact(db, execution, t1)
        db.commit()

        plan_id = plan.id; run_id = run.id; exec_id = execution.id; t1_id = t1.id; t2_id = t2.id

    try:
        with SessionLocal() as db:
            src_task = db.get(Task, t1_id)
            tgt_task = db.get(Task, t2_id)
            assert src_task is not None and tgt_task is not None

            h1 = create_agent_handoff(db, run_id, exec_id, src_task, tgt_task)
            db.commit()
            assert h1 is not None
            assert h1.workflow_run_id == run_id
            assert h1.source_agent_id == "researcher"
            assert h1.target_agent_id == "developer"
            assert artifact.id in h1.artifact_ids

            # Calling again must be idempotent and return the existing record
            h2 = create_agent_handoff(db, run_id, exec_id, src_task, tgt_task)
            assert h2 is not None
            assert h2.id == h1.id

            all_handoffs = list(db.scalars(select(AgentHandoff).where(AgentHandoff.workflow_run_id == run_id)).all())
            assert len(all_handoffs) == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_orchestrator_flow_creates_handoff_and_timeline_returns_it() -> None:
    agent = _MockAgentService()
    exec_service = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orchestrator = WorkflowOrchestrator(execution_service=exec_service, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan = Plan(title="Multi-agent Collaboration Plan", objective="Verify handoff between agents", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Research Requirements", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Develop Feature", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.flush()
        run = orchestrator.start_workflow(db, plan.id, uuid4().hex)
        plan_id = plan.id; run_id = run.id; t1_id = t1.id; t2_id = t2.id

    try:
        with SessionLocal() as db:
            claimed = orchestrator.claim_next(db, "test-worker")
            assert claimed is not None and claimed.id == run_id

        # Process the workflow until completion
        completed_run = await orchestrator.process(run_id, "test-worker")
        assert completed_run.status == "completed"

        with SessionLocal() as db:
            # Check executions
            exec1 = db.scalar(select(TaskExecution).where(TaskExecution.task_id == t1_id, TaskExecution.workflow_run_id == run_id))
            exec2 = db.scalar(select(TaskExecution).where(TaskExecution.task_id == t2_id, TaskExecution.workflow_run_id == run_id))
            assert exec1 is not None and exec2 is not None

            # Task 2 input snapshot must contain the structured handoff from researcher
            assert "Structured Handoff from Researcher AI to Developer AI" in (exec2.input_snapshot or "")
            assert "Key findings:" in (exec2.input_snapshot or "")

            # Verify handoffs table
            handoffs = list(db.scalars(select(AgentHandoff).where(AgentHandoff.workflow_run_id == run_id)).all())
            assert len(handoffs) == 1
            h = handoffs[0]
            assert h.source_agent_id == "researcher"
            assert h.target_agent_id == "developer"
            assert h.target_task_id == t2_id
            assert h.source_task_execution_id == exec1.id

            # Verify timeline response
            timeline = get_workflow_timeline(db, run_id)
            assert len(timeline.handoffs) == 1
            th = timeline.handoffs[0]
            assert th.source_agent_id == "researcher"
            assert th.target_agent_id == "developer"
            assert th.source_task_id == t1_id
            assert th.target_task_id == t2_id
            assert th.source_task_title == "Research Requirements"
            assert th.target_task_title == "Develop Feature"
            assert len(th.key_findings) > 0
            assert len(th.deliverables) > 0

        # Also verify via API endpoint
        with TestClient(app) as client:
            resp = client.get(f"/api/v1/workflows/{run_id}/timeline")
            assert resp.status_code == 200
            json_data = resp.json()
            assert "handoffs" in json_data
            assert len(json_data["handoffs"]) == 1
            assert json_data["handoffs"][0]["source_agent_name"] in ("Researcher", "Researcher AI")
            assert json_data["handoffs"][0]["target_agent_name"] in ("Developer", "Developer AI")

    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_handoff_isolation_between_runs() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Isolation Plan", objective="Verify no handoff cross-leak", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task A", status="done", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task B", status="done", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.flush()

        run1 = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=2, completed_tasks=2, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=10))
        run2 = WorkflowRun(plan_id=plan.id, status="completed", total_tasks=2, completed_tasks=2, idempotency_key=uuid4().hex, started_at=NOW - timedelta(minutes=5))
        db.add_all([run1, run2]); db.flush()

        exec1 = TaskExecution(task_id=t1.id, workflow_run_id=run1.id, agent_id="researcher", status="completed", input_snapshot="", output_content="Run 1 output", started_at=NOW - timedelta(minutes=9))
        exec2 = TaskExecution(task_id=t1.id, workflow_run_id=run2.id, agent_id="researcher", status="completed", input_snapshot="", output_content="Run 2 output", started_at=NOW - timedelta(minutes=4))
        db.add_all([exec1, exec2]); db.flush()

        h1 = AgentHandoff(workflow_run_id=run1.id, source_task_execution_id=exec1.id, source_agent_id="researcher", target_task_id=t2.id, target_agent_id="developer", summary="Handoff for Run 1", key_findings=["Finding 1"], deliverables=[], artifact_ids=[])
        h2 = AgentHandoff(workflow_run_id=run2.id, source_task_execution_id=exec2.id, source_agent_id="researcher", target_task_id=t2.id, target_agent_id="developer", summary="Handoff for Run 2", key_findings=["Finding 2"], deliverables=[], artifact_ids=[])
        db.add_all([h1, h2]); db.commit()

        plan_id = plan.id; run1_id = run1.id; run2_id = run2.id

    try:
        with SessionLocal() as db:
            timeline1 = get_workflow_timeline(db, run1_id)
            timeline2 = get_workflow_timeline(db, run2_id)

            assert len(timeline1.handoffs) == 1
            assert timeline1.handoffs[0].summary == "Handoff for Run 1"
            assert timeline1.handoffs[0].key_findings == ["Finding 1"]

            assert len(timeline2.handoffs) == 1
            assert timeline2.handoffs[0].summary == "Handoff for Run 2"
            assert timeline2.handoffs[0].key_findings == ["Finding 2"]
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()
