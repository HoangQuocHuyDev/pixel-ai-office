import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.exceptions import ApplicationError, WorkflowFencingError
from app.db.session import SessionLocal
from app.models.agent_handoff import AgentHandoff
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.ai import AIResponse
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import WorkflowOrchestrator, cancel_workflow


class FakeControlledAgentService:
    def __init__(self) -> None:
        self.call_count: dict[str, int] = {}
        self.sleep_seconds: float = 0.0

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.call_count[agent_id] = self.call_count.get(agent_id, 0) + 1
        if self.sleep_seconds > 0:
            await asyncio.sleep(self.sleep_seconds)
        return AIResponse(
            provider="fake",
            model="fake-gemini",
            content=f"Report output for {agent_id}.\n- Result detail 1\n- Result detail 2\nDeliverables:\n- Work Completed",
        )


def _setup_fencing_plan(db, task_count: int = 2) -> tuple[int, list[int]]:
    plan = Plan(
        title="Fencing Hardening Plan",
        objective="Verify ownership fencing and concurrency hardening",
        status="approved",
        idempotency_key=uuid4().hex,
        proposal_hash=uuid4().hex,
    )
    db.add(plan)
    db.flush()
    tasks = []
    agents = ["researcher", "developer"]
    for i in range(1, task_count + 1):
        t = Task(
            title=f"Fencing Task {i}",
            status="todo",
            priority="medium",
            assigned_agent_id=agents[(i - 1) % 2],
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


# 1. test_generation_increases_on_reclaim
def test_generation_increases_on_reclaim() -> None:
    with SessionLocal() as db:
        plan_id, _ = _setup_fencing_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        assert run.lease_generation == 0

    try:
        with SessionLocal() as db:
            claim1 = orch.claim_next(db, "worker-1")
            assert claim1 is not None and claim1.id == run_id
            assert claim1.lease_generation == 1
            assert claim1.lease_owner == "worker-1"

            # Expire lease
            claim1.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        with SessionLocal() as db:
            claim2 = orch.claim_next(db, "worker-2")
            assert claim2 is not None and claim2.id == run_id
            assert claim2.lease_generation == 2
            assert claim2.lease_owner == "worker-2"

            # Expire lease again
            claim2.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        with SessionLocal() as db:
            claim3 = orch.claim_next(db, "worker-3")
            assert claim3 is not None and claim3.id == run_id
            assert claim3.lease_generation == 3
            assert claim3.lease_owner == "worker-3"
    finally:
        _cleanup(plan_id)


# 2. test_heartbeat_does_not_increase_generation
def test_heartbeat_does_not_increase_generation() -> None:
    with SessionLocal() as db:
        plan_id, _ = _setup_fencing_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        with SessionLocal() as db:
            claim = orch.claim_next(db, "worker-1")
            assert claim is not None and claim.id == run_id
            assert claim.lease_generation == 1
            initial_expires = claim.lease_expires_at

            # Heartbeat 1
            orch._heartbeat(db, claim, "worker-1", expected_generation=1)
            assert claim.lease_generation == 1
            assert claim.lease_expires_at is not None and claim.lease_expires_at >= initial_expires

            # Heartbeat 2 via renew_lease
            renew_ok = orch._renew_lease(run_id, "worker-1", expected_generation=1)
            assert renew_ok is True

            db.refresh(claim)
            assert claim.lease_generation == 1
    finally:
        _cleanup(plan_id)


# 3. test_worker_a_late_success_rejected
def test_worker_a_late_success_rejected() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            claim1 = orch.claim_next(db, "worker-A")
            assert claim1 is not None and claim1.lease_generation == 1

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id
            assert execution.execution_lease_generation == 1
            assert execution.status == "running"

        # Worker A loses lease: Worker B reclaims
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        with SessionLocal() as db:
            claim2 = orch.claim_next(db, "worker-B")
            assert claim2 is not None and claim2.lease_generation == 2

        # Worker A tries to commit late success with old generation and old owner
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Worker A late success output",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )

        # Verify DB state was NOT modified by Worker A
        with SessionLocal() as db:
            e = db.get(TaskExecution, exec_id)
            assert e.status != "completed"
            assert e.output_content != "Worker A late success output"
            t = db.get(Task, task_id)
            assert t.status != "done"
    finally:
        _cleanup(plan_id)


# 4. test_worker_a_late_failure_rejected
def test_worker_a_late_failure_rejected() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Worker B reclaims workflow
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()
            orch.claim_next(db, "worker-B")

        # Worker A attempts late failure commit
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    error_code="AI_PROVIDER_ERROR",
                    error_message="Worker A failed late",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )
    finally:
        _cleanup(plan_id)


# 5. test_worker_b_recovery_unaffected
@pytest.mark.anyio
async def test_worker_b_recovery_unaffected() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )

        # Worker A crashes: expire lease
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        # Worker B claims and processes workflow to completion
        with SessionLocal() as db:
            claim_b = orch.claim_next(db, "worker-B")
            assert claim_b is not None and claim_b.lease_generation == 2

        completed_run = await orch.process(run_id, "worker-B")
        assert completed_run.status == "completed"
        assert completed_run.completed_tasks == 1

        with SessionLocal() as db:
            t = db.get(Task, task_id)
            assert t.status == "done"
    finally:
        _cleanup(plan_id)


# 6. test_cancellation_before_completion
def test_cancellation_before_completion() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Cancel workflow
        with SessionLocal() as db:
            cancelled_run = cancel_workflow(db, run_id)
            assert cancelled_run.status == "cancelled"

        # Worker A attempts late completion
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Worker A completed after cancellation",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )

        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            assert r.status == "cancelled"
            t = db.get(Task, task_id)
            assert t.status != "done"
    finally:
        _cleanup(plan_id)


# 7. test_completion_before_cancellation
def test_completion_before_cancellation() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Worker A completes legitimately
        with SessionLocal() as db:
            completed_exec = exec_svc._finish(
                db,
                exec_id,
                output="Legitimate output",
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            assert completed_exec.status == "completed"

        # Later cancellation does not revert completed execution
        with SessionLocal() as db:
            cancel_workflow(db, run_id)
            e = db.get(TaskExecution, exec_id)
            assert e.status == "completed"
            t = db.get(Task, task_id)
            assert t.status == "done"
    finally:
        _cleanup(plan_id)


# 8. test_no_artifact_from_stale_execution
def test_no_artifact_from_stale_execution() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Invalidate lease
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_generation = 2
            r.lease_owner = "worker-B"
            db.commit()

        # Fenced finish attempt
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Unauthorized deliverable",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )

        # Verify no artifact created
        with SessionLocal() as db:
            artifacts = list(db.scalars(select(Artifact).where(Artifact.task_execution_id == exec_id)).all())
            assert len(artifacts) == 0
    finally:
        _cleanup(plan_id)


# 9. test_no_handoff_from_stale_execution
def test_no_handoff_from_stale_execution() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 2)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_1 = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_1,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Worker B takes over
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_generation = 2
            r.lease_owner = "worker-B"
            db.commit()

        # Late finish from Worker A fails
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Fenced output",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )

        # Verify no handoffs created from this execution
        with SessionLocal() as db:
            handoffs = list(db.scalars(select(AgentHandoff).where(AgentHandoff.source_task_execution_id == exec_id)).all())
            assert len(handoffs) == 0
    finally:
        _cleanup(plan_id)


# 10. test_no_duplicate_progress
@pytest.mark.anyio
async def test_no_duplicate_progress() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 2)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        # Worker A executes task 1
        with SessionLocal() as db:
            e1, _ = exec_svc._start(db, task_ids[0], workflow_run_id=run_id, lease_generation=1, worker_id="worker-A")
            exec_svc._finish(db, e1.id, output="Valid task 1", workflow_run_id=run_id, lease_generation=1, worker_id="worker-A")
            r = db.get(WorkflowRun, run_id)
            r.completed_tasks = 1
            db.commit()

        # Worker A attempts to finish e1 again or late finish with wrong generation
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(db, e1.id, output="Duplicate task 1", workflow_run_id=run_id, lease_generation=2, worker_id="worker-A")

        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            assert r.completed_tasks == 1
    finally:
        _cleanup(plan_id)


# 11. test_concurrent_worker_claim
def test_concurrent_worker_claim() -> None:
    with SessionLocal() as db:
        plan_id, _ = _setup_fencing_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        with SessionLocal() as db1, SessionLocal() as db2:
            claim1 = orch.claim_next(db1, "worker-concurrent-1")
            claim2 = orch.claim_next(db2, "worker-concurrent-2")

            # Exactly one worker wins due to SKIP LOCKED
            assert (claim1 is not None and claim2 is None) or (claim1 is None and claim2 is not None)
            claimed = claim1 or claim2
            assert claimed.id == run_id
            assert claimed.lease_generation == 1
    finally:
        _cleanup(plan_id)


# 12. test_manual_execution_compatibility
@pytest.mark.anyio
async def test_manual_execution_compatibility() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)

    with SessionLocal() as db:
        task = Task(
            title="Manual Task Without Workflow",
            status="todo",
            priority="medium",
            assigned_agent_id="developer",
        )
        db.add(task)
        db.commit()
        task_id = task.id

    try:
        with SessionLocal() as db:
            execution = await exec_svc.execute(db, task_id)
            assert execution.status == "completed"
            assert execution.workflow_run_id is None
            assert execution.execution_lease_generation is None

        with SessionLocal() as db:
            t = db.get(Task, task_id)
            assert t.status == "done"
            art = db.scalar(select(Artifact).where(Artifact.task_execution_id == execution.id))
            assert art is not None
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.id == task_id))
            db.commit()


# 13. test_final_report_late_response_rejected
@pytest.mark.anyio
async def test_final_report_late_response_rejected() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

        # Mark all tasks done so workflow is ready for finalization
        for tid in task_ids:
            t = db.get(Task, tid)
            t.status = "done"
        db.commit()

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        # Worker A enters finalize_workflow, but during AI call lease expires and Worker B reclaims
        original_generate = exec_svc.generate_response_with_retry

        async def mocked_late_generate(*args, **kwargs):
            # Simulate lease loss before AI returns
            with SessionLocal() as db:
                r = db.get(WorkflowRun, run_id)
                r.lease_generation = 2
                r.lease_owner = "worker-B"
                db.commit()
            return await original_generate(*args, **kwargs)

        exec_svc.generate_response_with_retry = mocked_late_generate  # type: ignore[method-assign]

        result = await orch.finalize_workflow(run_id, "worker-A")
        # Result should not be completed by Worker A
        assert result.status != "completed" or result.final_report is None

        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            assert r.lease_owner == "worker-B"
            assert r.lease_generation == 2
            assert r.final_report is None
    finally:
        _cleanup(plan_id)


# 14. test_final_report_artifact_uniqueness
@pytest.mark.anyio
async def test_final_report_artifact_uniqueness() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-final")

        res = await orch.process(run_id, "worker-final")
        assert res.status == "completed"
        assert res.final_report is not None

        # Verify only 1 workflow final report artifact was created
        with SessionLocal() as db:
            artifacts = list(db.scalars(
                select(Artifact).where(Artifact.workflow_run_id == run_id, Artifact.artifact_type == "report")
            ).all())
            assert len(artifacts) == 1

        # Second call to finalize_workflow should be idempotent and not create duplicate artifact
        await orch.finalize_workflow(run_id, "worker-final")
        with SessionLocal() as db:
            artifacts = list(db.scalars(
                select(Artifact).where(Artifact.workflow_run_id == run_id, Artifact.artifact_type == "report")
            ).all())
            assert len(artifacts) == 1
    finally:
        _cleanup(plan_id)


# 15. test_lease_expiration_enforcement
def test_lease_expiration_enforcement() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-A")

        with SessionLocal() as db:
            execution, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-A",
            )
            exec_id = execution.id

        # Worker A's lease expires without any other worker claiming
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=15)
            db.commit()

        # Worker A attempts to finish execution after lease expired
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Expired lease result",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-A",
                )
    finally:
        _cleanup(plan_id)


# 16. test_same_worker_id_aba_protection
def test_same_worker_id_aba_protection() -> None:
    fake_ai = FakeControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _setup_fencing_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

    try:
        # Worker X claims run (Generation 1)
        with SessionLocal() as db:
            claim1 = orch.claim_next(db, "worker-X")
            assert claim1.lease_generation == 1

        # Worker X starts execution 1
        with SessionLocal() as db:
            execution1, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=1,
                worker_id="worker-X",
            )
            exec_id_1 = execution1.id
            assert execution1.execution_lease_generation == 1

        # Worker X crashes and restarts with the SAME worker_id "worker-X"
        # Lease expires
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        # Worker X (restarted) claims workflow -> Generation becomes 2!
        with SessionLocal() as db:
            claim2 = orch.claim_next(db, "worker-X")
            assert claim2.lease_generation == 2
            assert claim2.lease_owner == "worker-X"

        # Worker X (restarted) recovers stale execution 1 and starts execution 2
        with SessionLocal() as db:
            execution2, _ = exec_svc._start(
                db,
                task_id,
                workflow_run_id=run_id,
                lease_generation=2,
                worker_id="worker-X",
            )
            exec_id_2 = execution2.id
            assert execution2.execution_lease_generation == 2

        # Old in-flight Gemini response for execution 1 arrives with lease_generation=1 and worker_id="worker-X"
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id_1,
                    output="Old generation output from first instance",
                    workflow_run_id=run_id,
                    lease_generation=1,
                    worker_id="worker-X",
                )

        # Execution 2 finishes legitimately with lease_generation=2
        with SessionLocal() as db:
            completed2 = exec_svc._finish(
                db,
                exec_id_2,
                output="Legitimate output from second instance",
                workflow_run_id=run_id,
                lease_generation=2,
                worker_id="worker-X",
            )
            assert completed2.status == "completed"
            assert completed2.output_content == "Legitimate output from second instance"

        # Verify final state
        with SessionLocal() as db:
            e1 = db.get(TaskExecution, exec_id_1)
            e2 = db.get(TaskExecution, exec_id_2)
            assert e1.status != "completed"
            assert e2.status == "completed"
    finally:
        _cleanup(plan_id)
