import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.exceptions import ApplicationError
from app.db.session import SessionLocal
from app.models.agent_handoff import AgentHandoff
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.ai import AIResponse
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    cancel_workflow,
    check_retry_eligibility,
    get_retry_run_ids,
    get_workflow_failure_info,
    serialize_workflow_run,
)
from app.services.workflow_timeline_service import get_workflow_timeline


class ControlledAgentService:
    def __init__(self) -> None:
        self.call_count: dict[str, int] = {}
        self.fail_task_id: int | None = None
        self.fail_error: ApplicationError | None = None

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.call_count[agent_id] = self.call_count.get(agent_id, 0) + 1
        if self.fail_task_id is not None and f"Task title: Task {self.fail_task_id}" in prompt:
            if self.fail_error is not None:
                raise self.fail_error
            raise ApplicationError(500, "AI_EXECUTION_FAILED", "Simulated AI execution failure.")
        return AIResponse(
            provider="mock",
            model="mock-gemini",
            content=f"Report output for {agent_id}.\n- Result detail\nDeliverables:\n- Work Item",
        )


def _setup_plan(db, task_count: int = 3) -> tuple[int, list[int]]:
    plan = Plan(
        title="Recovery Verification Plan",
        objective="Verify safe workflow retry and recovery mechanisms",
        status="approved",
        idempotency_key=uuid4().hex,
        proposal_hash=uuid4().hex,
    )
    db.add(plan)
    db.flush()
    tasks = []
    agents = ["developer", "researcher", "developer"]
    for i in range(1, task_count + 1):
        t = Task(
            title=f"Task {i}",
            description=f"Description for task {i}",
            status="todo",
            priority="medium",
            assigned_agent_id=agents[(i - 1) % len(agents)],
            plan_id=plan.id,
            sequence_order=i,
        )
        tasks.append(t)
    db.add_all(tasks)
    db.commit()
    return plan.id, [t.id for t in tasks]


def _cleanup(plan_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(Task).where(Task.plan_id == plan_id))
        db.execute(delete(Plan).where(Plan.id == plan_id))
        db.commit()


# 1. test_retry_failed_run_creates_new_run
def test_retry_failed_run_creates_new_run() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

        # Mark run failed
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Task 1 failed.")

    try:
        with SessionLocal() as db:
            new_run = orch.retry_workflow(db, run_id)
            assert new_run.id != run_id
            assert new_run.status == "pending"
            assert new_run.plan_id == plan_id
            assert new_run.retried_from_run_id == run_id
            assert new_run.lease_generation == 0
            assert new_run.lease_owner is None
    finally:
        _cleanup(plan_id)


# 2. test_old_run_remains_failed
def test_old_run_remains_failed() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 2)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Fatal failure.")
        failed_at = run.completed_at

    try:
        with SessionLocal() as db:
            new_run = orch.retry_workflow(db, run_id)
            new_run_id = new_run.id

        with SessionLocal() as db:
            old_run = db.get(WorkflowRun, run_id)
            assert old_run.status == "failed"
            assert old_run.error_code == "TASK_EXECUTION_FAILED"
            assert old_run.completed_at == failed_at
    finally:
        _cleanup(plan_id)


# 3. test_retry_lineage_correct
def test_retry_lineage_correct() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        orch._fail(db, run, "INTERRUPTED_EXECUTION", "Worker died.")

    try:
        with SessionLocal() as db:
            new_run = orch.retry_workflow(db, run_id)
            new_id = new_run.id

        with SessionLocal() as db:
            retry_ids = get_retry_run_ids(db, run_id)
            assert retry_ids == [new_id]

            nr = db.get(WorkflowRun, new_id)
            assert nr.retried_from_run_id == run_id
    finally:
        _cleanup(plan_id)


# 4. test_retry_completed_rejected
def test_retry_completed_rejected() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        run_id = run.id

    try:
        with SessionLocal() as db:
            with pytest.raises(ApplicationError) as exc_info:
                orch.retry_workflow(db, run_id)
            assert exc_info.value.status_code == 409
            assert exc_info.value.error_code == "WORKFLOW_NOT_FAILED"
    finally:
        _cleanup(plan_id)


# 5. test_retry_running_rejected
def test_retry_running_rejected() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch.claim_next(db, "worker-test")
        run_id = run.id

    try:
        with SessionLocal() as db:
            with pytest.raises(ApplicationError) as exc_info:
                orch.retry_workflow(db, run_id)
            assert exc_info.value.status_code == 409
            assert exc_info.value.error_code == "WORKFLOW_NOT_FAILED"
    finally:
        _cleanup(plan_id)


# 6. test_retry_cancelled_rejected
def test_retry_cancelled_rejected() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        cancel_workflow(db, run_id)

    try:
        with SessionLocal() as db:
            with pytest.raises(ApplicationError) as exc_info:
                orch.retry_workflow(db, run_id)
            assert exc_info.value.status_code == 409
            assert exc_info.value.error_code == "WORKFLOW_NOT_FAILED"
    finally:
        _cleanup(plan_id)


# 7. test_retry_permanent_error_blocked
def test_retry_permanent_error_blocked() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch._fail(db, run, "AI_CONFIG_ERROR", "Invalid model configuration specified.")
        run_id = run.id

    try:
        with SessionLocal() as db:
            can_retry, reason = check_retry_eligibility(db, run)
            assert can_retry is False
            assert "AI_CONFIG_ERROR" in (reason or "")

            with pytest.raises(ApplicationError) as exc_info:
                orch.retry_workflow(db, run_id)
            assert exc_info.value.status_code == 422
            assert exc_info.value.error_code == "WORKFLOW_NON_RETRYABLE"
    finally:
        _cleanup(plan_id)


# 8. test_retry_transient_error_allowed
def test_retry_transient_error_allowed() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch._fail(db, run, "AI_EXECUTION_TIMEOUT", "AI service call timed out.")
        run_id = run.id

    try:
        with SessionLocal() as db:
            can_retry, reason = check_retry_eligibility(db, run)
            assert can_retry is True
            assert reason is None

            new_run = orch.retry_workflow(db, run_id)
            assert new_run.status == "pending"
    finally:
        _cleanup(plan_id)


# 9. test_active_run_conflict
def test_active_run_conflict() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id
        orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Failed once.")

        # Another active run was started on the same plan
        run2 = orch.start_workflow(db, plan_id, uuid4().hex)

    try:
        with SessionLocal() as db:
            with pytest.raises(ApplicationError) as exc_info:
                orch.retry_workflow(db, run1_id)
            assert exc_info.value.status_code == 409
            assert exc_info.value.error_code == "WORKFLOW_ALREADY_ACTIVE"
    finally:
        _cleanup(plan_id)


# 10. test_concurrent_duplicate_retry_request
def test_concurrent_duplicate_retry_request() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Failed.")
        run_id = run.id

    try:
        shared_key = uuid4().hex
        with SessionLocal() as db1:
            retry1 = orch.retry_workflow(db1, run_id, idempotency_key=shared_key)

        with SessionLocal() as db2:
            retry2 = orch.retry_workflow(db2, run_id, idempotency_key=shared_key)

        assert retry1.id == retry2.id
    finally:
        _cleanup(plan_id)


# 11. test_retry_after_previous_retry_failed
def test_retry_after_previous_retry_failed() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Failed run 1.")
        run1_id = run1.id

    try:
        # Retry Run 1 -> Run 2
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            assert run2.retried_from_run_id == run1_id
            orch._fail(db, run2, "TASK_EXECUTION_FAILED", "Failed run 2.")

        # Retry Run 2 -> Run 3
        with SessionLocal() as db:
            run3 = orch.retry_workflow(db, run2_id)
            run3_id = run3.id
            assert run3.retried_from_run_id == run2_id

        # Verify lineage links
        with SessionLocal() as db:
            assert get_retry_run_ids(db, run1_id) == [run2_id]
            assert get_retry_run_ids(db, run2_id) == [run3_id]
            assert get_retry_run_ids(db, run3_id) == []
    finally:
        _cleanup(plan_id)


# 12. test_new_run_fencing_generation
def test_new_run_fencing_generation() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        orch.claim_next(db, "worker-1")  # Gen becomes 1
        orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Failed.")
        run1_id = run1.id

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            assert run2.lease_generation == 0

            # When claimed by worker, generation increments to 1
            claim2 = orch.claim_next(db, "worker-2")
            assert claim2.id == run2.id
            assert claim2.lease_generation == 1
    finally:
        _cleanup(plan_id)


# 13. test_no_old_execution_mutation
def test_no_old_execution_mutation() -> None:
    fake_ai = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id
        orch.claim_next(db, "worker-1")

        # Execute task 1
        e1, _ = exec_svc._start(db, task_ids[0], workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        exec_svc._finish(db, e1.id, output="Output task 1", workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")

        # Execute task 2 and fail
        e2, _ = exec_svc._start(db, task_ids[1], workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        exec_svc._finish(db, e2.id, error_code="TASK_FAILED", error_message="Task 2 error", workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        orch._fail(db, run1, "TASK_FAILED", "Workflow failed on task 2.")

        e1_id = e1.id
        e2_id = e2.id

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)

        # Verify old executions are completely unchanged
        with SessionLocal() as db:
            old_e1 = db.get(TaskExecution, e1_id)
            old_e2 = db.get(TaskExecution, e2_id)
            assert old_e1.workflow_run_id == run1_id
            assert old_e1.status == "completed"
            assert old_e2.workflow_run_id == run1_id
            assert old_e2.status == "failed"
    finally:
        _cleanup(plan_id)


# 14. test_no_old_artifact_mutation
def test_no_old_artifact_mutation() -> None:
    fake_ai = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id
        orch.claim_next(db, "worker-1")

        e1, _ = exec_svc._start(db, task_ids[0], workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        exec_svc._finish(db, e1.id, output="Deliverable output", workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        orch._fail(db, run1, "TASK_FAILED", "Failed.")

        art1 = db.scalar(select(Artifact).where(Artifact.task_execution_id == e1.id))
        assert art1 is not None
        art1_id = art1.id

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)

        with SessionLocal() as db:
            a = db.get(Artifact, art1_id)
            assert a.task_execution_id == e1.id
            assert a.title.startswith("Task 1")
    finally:
        _cleanup(plan_id)


# 15. test_no_cross_run_handoff_contamination
def test_no_cross_run_handoff_contamination() -> None:
    fake_ai = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id
        orch.claim_next(db, "worker-1")

        e1, _ = exec_svc._start(db, task_ids[0], workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")
        exec_svc._finish(db, e1.id, output="Task 1 done", workflow_run_id=run1_id, lease_generation=1, worker_id="worker-1")

        # Handoff created for Run 1
        t1 = db.get(Task, task_ids[0])
        t2 = db.get(Task, task_ids[1])
        from app.services.handoff_service import create_agent_handoff
        h = create_agent_handoff(db, run1_id, e1.id, t1, t2)
        db.commit()
        handoff_id = h.id

        orch._fail(db, run1, "TASK_FAILED", "Failed on task 2.")

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id

        with SessionLocal() as db:
            h_record = db.get(AgentHandoff, handoff_id)
            assert h_record.workflow_run_id == run1_id
            # No handoffs created in run 2 yet
            run2_handoffs = list(db.scalars(select(AgentHandoff).where(AgentHandoff.workflow_run_id == run2_id)).all())
            assert len(run2_handoffs) == 0
    finally:
        _cleanup(plan_id)


# 16. test_task_status_consistency
def test_task_status_consistency() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 3)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

        # Task 1 done, Task 2 in_progress when crash occurs
        t1 = db.get(Task, task_ids[0])
        t1.status = "done"
        db.add(TaskExecution(
            task_id=task_ids[0],
            workflow_run_id=run1_id,
            agent_id="developer",
            status="completed",
            input_snapshot="test",
            output_content="result",
            completed_at=datetime.now(timezone.utc),
        ))
        t2 = db.get(Task, task_ids[1])
        t2.status = "in_progress"
        db.commit()

        orch._fail(db, run1, "WORKFLOW_ATTEMPTS_EXHAUSTED", "Worker lost.")

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)

        with SessionLocal() as db:
            t1 = db.get(Task, task_ids[0])
            t2 = db.get(Task, task_ids[1])
            t3 = db.get(Task, task_ids[2])
            assert t1.status == "done"  # Preserved!
            assert t2.status == "todo"  # Normalized from in_progress
            assert t3.status == "todo"
            assert run2.completed_tasks == 1
            assert run2.total_tasks == 3
    finally:
        _cleanup(plan_id)


# 17. test_timeline_lineage_serialization
def test_timeline_lineage_serialization() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id
        orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Task 1 failed.")

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id

        with SessionLocal() as db:
            tl1 = get_workflow_timeline(db, run1_id)
            assert tl1.can_retry is False  # Because plan currently has active run2
            assert tl1.retry_run_ids == [run2_id]
            assert tl1.retried_from_run_id is None

            tl2 = get_workflow_timeline(db, run2_id)
            assert tl2.retried_from_run_id == run1_id
            assert tl2.retry_run_ids == []
    finally:
        _cleanup(plan_id)


# 18. test_retry_e2e_resumes_from_failed_task
@pytest.mark.anyio
async def test_retry_e2e_resumes_from_failed_task() -> None:
    fake_ai = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 3)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        # Step 1: Run 1 executes Task 1 successfully, then Task 2 fails
        with SessionLocal() as db:
            orch.claim_next(db, "worker-1")

        # Cause task 2 to fail
        fake_ai.fail_task_id = 2

        res1 = await orch.process(run1_id, "worker-1")
        assert res1.status == "failed"

        with SessionLocal() as db:
            t1 = db.get(Task, task_ids[0])
            t2 = db.get(Task, task_ids[1])
            assert t1.status == "done"
            assert t2.status == "todo"

        # Step 2: Fix the issue (clear failure simulation) and user retries
        fake_ai.fail_task_id = None

        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            assert run2.completed_tasks == 1  # Preserves Task 1!

        # Step 3: Worker claims Run 2 and processes
        with SessionLocal() as db:
            claim2 = orch.claim_next(db, "worker-2")
            assert claim2 is not None and claim2.id == run2_id

        res2 = await orch.process(run2_id, "worker-2")
        assert res2.status == "completed"
        assert res2.completed_tasks == 3
        assert res2.final_report is not None

        # Verify all tasks are done
        with SessionLocal() as db:
            for tid in task_ids:
                t = db.get(Task, tid)
                assert t.status == "done"

            # Check timeline of Run 2: Task 1 was pre_existing, Tasks 2 and 3 executed
            tl2 = get_workflow_timeline(db, run2_id)
            assert tl2.steps[0].pre_existing is True
            assert tl2.steps[0].status == "completed"
            assert tl2.steps[1].pre_existing is False
            assert tl2.steps[1].status == "completed"
            assert tl2.steps[2].status == "completed"
            assert tl2.status == "completed"
    finally:
        _cleanup(plan_id)

