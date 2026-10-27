import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.agents.registry import default_agent_registry
from app.core.exceptions import ApplicationError, WorkflowFencingError
from app.db.session import SessionLocal
from app.services.agent_activity_service import list_agent_activities
from app.models.agent_handoff import AgentHandoff
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.ai import AIResponse
from app.schemas.planning import PlanApproveRequest
from app.services.artifact_service import (
    create_execution_artifact,
    create_workflow_artifact,
    get_artifact,
    list_artifacts,
)
from app.services.artifact_version_service import list_versions
from app.services.handoff_service import create_agent_handoff
from app.services.planning_service import PlanningService
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    cancel_workflow,
    check_retry_eligibility,
    get_retry_ancestor_ids,
)
from app.services.workflow_timeline_service import get_workflow_timeline


class E2EControlledAgentService:
    def __init__(self, fail_task_number: int | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_task_number = fail_task_number

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.calls.append((agent_id, prompt))
        if self.fail_task_number is not None and f"Task title: Task {self.fail_task_number}" in prompt:
            raise ApplicationError(504, "AI_EXECUTION_TIMEOUT", f"Simulated timeout on task {self.fail_task_number}")
        return AIResponse(
            provider="mock-provider",
            model="gemini-3.5-flash-mock",
            content=(
                f"### Output by {agent_id.upper()}\n"
                f"- Analysis finding 1 for {prompt[:25]}...\n"
                f"- Analysis finding 2\n"
                f"Deliverables:\n"
                f"- Work specification document\n"
                f"- Implementation deliverable"
            ),
        )


def _cleanup(plan_id: int) -> None:
    with SessionLocal() as db:
        run_ids = list(db.scalars(select(WorkflowRun.id).where(WorkflowRun.plan_id == plan_id)).all())
        if run_ids:
            db.execute(delete(AgentHandoff).where(AgentHandoff.workflow_run_id.in_(run_ids)))
            db.execute(delete(Artifact).where(Artifact.workflow_run_id.in_(run_ids)))
            db.execute(delete(TaskExecution).where(TaskExecution.workflow_run_id.in_(run_ids)))
            db.execute(delete(WorkflowRun).where(WorkflowRun.plan_id == plan_id))
        task_ids = list(db.scalars(select(Task.id).where(Task.plan_id == plan_id)).all())
        if task_ids:
            db.execute(delete(TaskExecution).where(TaskExecution.task_id.in_(task_ids)))
        db.execute(delete(Task).where(Task.plan_id == plan_id))
        db.execute(delete(Plan).where(Plan.id == plan_id))
        db.commit()


# SCENARIO A: Complete Workflow Lifecycle
@pytest.mark.anyio
async def test_scenario_a_complete_workflow_lifecycle() -> None:
    fake_ai = E2EControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    # 1. User prompts -> Manager creates Plan -> User Approves Plan
    approve_req = PlanApproveRequest.model_validate({
        "idempotency_key": "plan-appr-" + uuid4().hex,
        "proposal": {
            "title": "E2E Complete Plan",
            "objective": "Verify complete lifecycle end to end",
            "tasks": [
                {
                    "title": "Task 1",
                    "description": "Perform background research",
                    "priority": "high",
                    "assigned_agent_id": "researcher",
                    "sequence_order": 1,
                },
                {
                    "title": "Task 2",
                    "description": "Develop implementation based on research",
                    "priority": "high",
                    "assigned_agent_id": "developer",
                    "sequence_order": 2,
                },
            ],
        },
    })
    with SessionLocal() as db:
        plan = PlanningService().approve(db, approve_req)
        plan_id = plan.id

    try:
        # 2. Start Workflow
        workflow_key = "wf-start-" + uuid4().hex
        with SessionLocal() as db:
            run = orch.start_workflow(db, plan_id, workflow_key)
            run_id = run.id
            assert run.status == "pending"
            assert run.total_tasks == 2
            assert run.completed_tasks == 0

        # 3. Worker claims workflow
        with SessionLocal() as db:
            claimed = orch.claim_next(db, "worker-e2e")
            assert claimed is not None and claimed.id == run_id
            assert claimed.status == "running"
            assert claimed.lease_owner == "worker-e2e"

        # 4. Worker processes workflow (Task 1 -> Task 2 -> Final Report)
        result = await orch.process(run_id, "worker-e2e")
        assert result.status == "completed"
        assert result.completed_tasks == 2
        assert result.final_report is not None
        assert "MANAGER" in result.final_report or "Output by" in result.final_report

        # 5. Verify Call Chain: Researcher -> Developer -> Manager
        assert len(fake_ai.calls) == 3
        assert fake_ai.calls[0][0] == "researcher"
        assert fake_ai.calls[1][0] == "developer"
        assert fake_ai.calls[2][0] == "manager"

        # Developer prompt received untrusted reference / handoff context from Researcher
        assert "Task 1" in fake_ai.calls[1][1] or "Reference results" in fake_ai.calls[1][1]

        # 6. Verify Database State
        with SessionLocal() as db:
            tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
            assert all(t.status == "done" for t in tasks)

            executions = list(db.scalars(
                select(TaskExecution).where(TaskExecution.workflow_run_id == run_id).order_by(TaskExecution.id)
            ).all())
            assert len(executions) == 2
            assert all(e.status == "completed" for e in executions)

            # Check Artifacts: 2 task artifacts + 1 workflow report artifact = 3 artifacts
            exec_ids = [e.id for e in executions]
            task_artifacts = list(db.scalars(
                select(Artifact).where(Artifact.task_execution_id.in_(exec_ids)).order_by(Artifact.id)
            ).all())
            wf_artifact = db.scalar(select(Artifact).where(Artifact.workflow_run_id == run_id))
            assert len(task_artifacts) == 2
            assert wf_artifact is not None

            # Check Handoff: 1 handoff generated from Task 1 to Task 2
            handoffs = list(db.scalars(
                select(AgentHandoff).where(AgentHandoff.workflow_run_id == run_id)
            ).all())
            assert len(handoffs) == 1
            assert handoffs[0].source_agent_id == "researcher"
            assert handoffs[0].target_agent_id == "developer"
            assert handoffs[0].target_task_id == tasks[1].id

            # 7. Timeline API
            timeline = get_workflow_timeline(db, run_id)
            assert timeline.status == "completed"
            assert timeline.progress.completed_tasks == 2
            assert timeline.progress.progress_percentage == 100.0
            assert len(timeline.steps) == 2
            assert timeline.steps[0].status == "completed"
            assert timeline.steps[1].status == "completed"
            assert timeline.finalization.status == "completed"
            assert len(timeline.handoffs) == 1

            # 8. Workspace & Artifact Viewer
            ws_wf_artifacts = list_artifacts(db, limit=50, offset=0, workflow_run_id=run_id)
            assert ws_wf_artifacts.total == 1
            assert ws_wf_artifacts.items[0].artifact_type == "report"

            ws_task1_artifacts = list_artifacts(db, limit=50, offset=0, task_id=tasks[0].id)
            assert ws_task1_artifacts.total == 1
            assert ws_task1_artifacts.items[0].agent_id == "researcher"

            ws_task2_artifacts = list_artifacts(db, limit=50, offset=0, task_id=tasks[1].id)
            assert ws_task2_artifacts.total == 1
            assert ws_task2_artifacts.items[0].agent_id == "developer"
            # Read first artifact
            art_detail = get_artifact(db, task_artifacts[0].id)
            assert art_detail.id == task_artifacts[0].id
            versions = list_versions(db, task_artifacts[0].id, limit=50, offset=0)
            assert len(versions.items) >= 1
    finally:
        _cleanup(plan_id)


# SCENARIO B: Multi-Agent Collaboration
@pytest.mark.anyio
async def test_scenario_b_multi_agent_collaboration() -> None:
    fake_ai = E2EControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan = Plan(
            title="Collab Plan",
            objective="Test Researcher and Developer Collaboration",
            status="approved",
            idempotency_key=uuid4().hex,
            proposal_hash=uuid4().hex,
        )
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="high", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.commit()
        plan_id = plan.id

    try:
        with SessionLocal() as db:
            run = orch.start_workflow(db, plan_id, uuid4().hex)
            run_id = run.id
            orch.claim_next(db, "w-collab")

        res = await orch.process(run_id, "w-collab")
        assert res.status == "completed"

        # Verify default registry roles
        assert default_agent_registry.get("researcher").name == "Researcher AI"
        assert default_agent_registry.get("developer").name == "Developer AI"
        assert default_agent_registry.get("manager").name == "Manager AI"

        with SessionLocal() as db:
            handoff = db.scalar(select(AgentHandoff).where(AgentHandoff.workflow_run_id == run_id))
            assert handoff is not None
            assert handoff.source_agent_id == "researcher"
            assert handoff.target_agent_id == "developer"
            assert len(handoff.key_findings) >= 1
            assert len(handoff.deliverables) >= 1
    finally:
        _cleanup(plan_id)


# SCENARIO C: Failure & Safe Retry
@pytest.mark.anyio
async def test_scenario_c_failure_and_safe_retry() -> None:
    fake_ai = E2EControlledAgentService(fail_task_number=2)
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan = Plan(
            title="Failure Plan",
            objective="Test safe retry after step failure",
            status="approved",
            idempotency_key=uuid4().hex,
            proposal_hash=uuid4().hex,
        )
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        t3 = Task(title="Task 3", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=3)
        db.add_all([t1, t2, t3]); db.commit()
        plan_id = plan.id

    try:
        # 1. Run 1 starts and fails on Task 2
        with SessionLocal() as db:
            run1 = orch.start_workflow(db, plan_id, uuid4().hex)
            run1_id = run1.id
            orch.claim_next(db, "w-run1")

        res1 = await orch.process(run1_id, "w-run1")
        assert res1.status == "failed"
        assert res1.error_code in ("AI_EXECUTION_TIMEOUT", "TASK_EXECUTION_FAILED")

        # 2. Check retry eligibility
        with SessionLocal() as db:
            run1_db = db.get(WorkflowRun, run1_id)
            can_retry, reason = check_retry_eligibility(db, run1_db)
            assert can_retry is True

            # 3. Create Retry Run 2
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            assert run2.status == "pending"
            assert run2.retried_from_run_id == run1_id
            assert run2.completed_tasks == 1  # Task 1 reused!

            # Old run is preserved as failed
            assert run1_db.status == "failed"

        # 4. Resolve failure and execute Run 2
        fake_ai.fail_task_number = None
        fake_ai.calls.clear()

        with SessionLocal() as db:
            orch.claim_next(db, "w-run2")

        res2 = await orch.process(run2_id, "w-run2")
        assert res2.status == "completed"

        # In Run 2: Task 1 was skipped; only Task 2, Task 3, and Manager executed
        assert [agent for agent, _ in fake_ai.calls] == ["developer", "researcher", "manager"]

        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run2_id)
            assert timeline.steps[0].pre_existing is True
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[1].reused_from_run_id is None
            assert timeline.steps[2].reused_from_run_id is None
            assert timeline.progress.completed_tasks == 3
    finally:
        _cleanup(plan_id)


# SCENARIO D: Multi-Generation Retry
@pytest.mark.anyio
async def test_scenario_d_multi_generation_retry() -> None:
    fake_ai = E2EControlledAgentService(fail_task_number=2)
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan = Plan(
            title="Multi Gen Plan",
            objective="Test 3 generations of retries",
            status="approved",
            idempotency_key=uuid4().hex,
            proposal_hash=uuid4().hex,
        )
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        t3 = Task(title="Task 3", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=3)
        db.add_all([t1, t2, t3]); db.commit()
        plan_id = plan.id

    try:
        # Gen 1: fails on Task 2
        with SessionLocal() as db:
            run1 = orch.start_workflow(db, plan_id, uuid4().hex)
            run1_id = run1.id
            orch.claim_next(db, "w1")
        await orch.process(run1_id, "w1")

        # Gen 2: Task 2 fails on Task 3
        fake_ai.fail_task_number = 3
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            orch.claim_next(db, "w2")
        await orch.process(run2_id, "w2")

        # Gen 3: completes
        fake_ai.fail_task_number = None
        fake_ai.calls.clear()
        with SessionLocal() as db:
            run3 = orch.retry_workflow(db, run2_id)
            run3_id = run3.id
            assert run3.completed_tasks == 2
            ancestors = get_retry_ancestor_ids(db, run3_id)
            assert ancestors == [run2_id, run1_id]
            orch.claim_next(db, "w3")

        res3 = await orch.process(run3_id, "w3")
        assert res3.status == "completed"

        # Gen 3 only ran Task 3 and Manager
        assert [agent for agent, _ in fake_ai.calls] == ["developer", "manager"]

        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run3_id)
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[1].reused_from_run_id == run2_id
            assert timeline.steps[2].reused_from_run_id is None
            assert timeline.progress.completed_tasks == 3
    finally:
        _cleanup(plan_id)


# SCENARIO E: Cancellation
@pytest.mark.anyio
async def test_scenario_e_cancellation_lifecycle() -> None:
    fake_ai = E2EControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan = Plan(title="Cancel Plan", objective="Test cancellation at all stages", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        db.add(t1); db.commit()
        plan_id = plan.id

    try:
        # 1. Cancel in pending state
        with SessionLocal() as db:
            run_pending = orch.start_workflow(db, plan_id, uuid4().hex)
            cancel_workflow(db, run_pending.id)
            assert run_pending.status == "cancelled"

        # 2. Cancel in running state
        plan2_req = PlanApproveRequest.model_validate({
            "idempotency_key": uuid4().hex,
            "proposal": {
                "title": "P2",
                "objective": "O2",
                "tasks": [{"title": "Task 1", "description": "Desc 1", "priority": "medium", "assigned_agent_id": "developer", "sequence_order": 1}],
            },
        })
        with SessionLocal() as db:
            plan2 = PlanningService().approve(db, plan2_req)
            plan2_id = plan2.id
            run_running = orch.start_workflow(db, plan2_id, uuid4().hex)
            orch.claim_next(db, "w-cancel")
            cancel_workflow(db, run_running.id)
            assert run_running.status == "cancelled"

        # 3. Cancel after completed is a safe no-op
        with SessionLocal() as db:
            run_running.status = "completed"
            db.commit()
            cancel_workflow(db, run_running.id)
            assert run_running.status == "completed"

        _cleanup(plan2_id)
    finally:
        _cleanup(plan_id)


# SCENARIO F: Worker Failure & Recovery
def test_scenario_f_worker_failure_and_recovery() -> None:
    orch = WorkflowOrchestrator(lease_seconds=1)
    with SessionLocal() as db:
        plan = Plan(title="Recovery Plan", objective="Test recovery", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        db.add(t1); db.commit()
        plan_id = plan.id

    try:
        with SessionLocal() as db:
            run = orch.start_workflow(db, plan_id, uuid4().hex)
            run_id = run.id

            # Worker 1 claims
            w1 = orch.claim_next(db, "worker-1")
            assert w1 is not None
            assert w1.lease_generation == 1

            # Worker 1 crashes (simulated by expired lease)
            w1.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=2)
            db.commit()

            # Worker 2 reclaims
            w2 = orch.claim_next(db, "worker-2")
            assert w2 is not None
            assert w2.lease_owner == "worker-2"
            assert w2.lease_generation == 2
    finally:
        _cleanup(plan_id)


# SCENARIO H: Manual Execution Interference
def test_scenario_h_manual_execution_interference() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan = Plan(title="Manual Plan", objective="Test manual interference", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.commit()
        plan_id = plan.id

    try:
        # Manual execution of Task 1 before workflow retry
        with SessionLocal() as db:
            run1 = orch.start_workflow(db, plan_id, uuid4().hex)
            run1_id = run1.id
            orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Workflow 1 failed")

            # Manually mark Task 1 done
            task1 = db.get(Task, t1.id)
            task1.status = "done"
            db.add(TaskExecution(
                task_id=task1.id, workflow_run_id=None, agent_id="developer",
                status="completed", input_snapshot="manual", output_content="manual out",
                completed_at=datetime.now(timezone.utc),
            ))
            db.commit()

            # Retry Workflow: Task 1 manual execution MUST NOT be reused!
            run2 = orch.retry_workflow(db, run1_id)
            assert run2.completed_tasks == 0
            task1_after = db.get(Task, t1.id)
            assert task1_after.status == "todo"
    finally:
        _cleanup(plan_id)


# SCENARIO I: Artifact & Handoff Integrity
def test_scenario_i_artifact_and_handoff_integrity() -> None:
    with SessionLocal() as db:
        plan = Plan(title="Artifact Plan", objective="Test artifact provenance", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Task 1", status="done", priority="medium", assigned_agent_id="researcher", plan_id=plan.id, sequence_order=1)
        t2 = Task(title="Task 2", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=2)
        db.add_all([t1, t2]); db.flush()
        run = WorkflowRun(plan_id=plan.id, status="running", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run); db.flush()

        exec1 = TaskExecution(
            task_id=t1.id, workflow_run_id=run.id, agent_id="researcher",
            status="completed", input_snapshot="in", output_content="research report",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(exec1); db.flush()

        # Create execution artifact
        artifact = create_execution_artifact(db, exec1, t1)
        assert artifact is not None
        assert artifact.task_execution_id == exec1.id
        assert artifact.task_id == t1.id

        # Create handoff
        handoff = create_agent_handoff(db, run.id, exec1.id, t1, t2)
        assert handoff.source_task_execution_id == exec1.id
        assert artifact.id in handoff.artifact_ids

        db.commit()
        plan_id = plan.id
        art_id = artifact.id

    try:
        with SessionLocal() as db:
            # Query artifact with version history
            art = get_artifact(db, art_id)
            assert art is not None
            versions = list_versions(db, art_id, limit=50, offset=0)
            assert len(versions.items) >= 1
            assert versions.items[0].version_number == 1
    finally:
        _cleanup(plan_id)


# SCENARIO K: Phaser Agent Sync Activity Logging
@pytest.mark.anyio
async def test_scenario_k_phaser_agent_sync_activity_logging() -> None:
    fake_ai = E2EControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)

    with SessionLocal() as db:
        plan = Plan(title="Phaser Plan", objective="Verify agent activity logging", status="approved", idempotency_key=uuid4().hex, proposal_hash=uuid4().hex)
        db.add(plan); db.flush()
        t1 = Task(title="Sync Task", status="todo", priority="medium", assigned_agent_id="developer", plan_id=plan.id, sequence_order=1)
        db.add(t1); db.commit()
        plan_id = plan.id
        task_id = t1.id

    try:
        with SessionLocal() as db:
            # Execute task via TaskExecutionService
            execution = await exec_svc.execute(db, task_id, "Context for task")
            assert execution.status == "completed"

            # Check that AgentActivity or Task status accurately transitioned
            t = db.get(Task, task_id)
            assert t.status == "done"

            # Query agent activities
            activities = list_agent_activities(db, datetime.now(timezone.utc))
            act_map = {a.agent_id: a for a in activities}
            assert "developer" in act_map
            assert "manager" in act_map
            assert "researcher" in act_map
    finally:
        _cleanup(plan_id)
