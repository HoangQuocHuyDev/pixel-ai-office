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
from app.services.artifact_service import create_execution_artifact, create_workflow_artifact
from app.services.handoff_service import create_agent_handoff
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import (
    MAX_FINALIZATION_ATTEMPTS,
    MAX_TASK_EXECUTION_ATTEMPTS,
    MAX_WORKFLOW_ATTEMPTS,
    WorkflowOrchestrator,
    cancel_workflow,
)

NOW = datetime.now(timezone.utc)


class ControlledAgentService:
    def __init__(self) -> None:
        self.call_count: dict[str, int] = {}
        self.fail_agent_id: str | None = None
        self.fail_error: ApplicationError | None = None
        self.fail_attempts_remaining: int = 0

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.call_count[agent_id] = self.call_count.get(agent_id, 0) + 1
        if self.fail_agent_id == agent_id and self.fail_attempts_remaining > 0:
            self.fail_attempts_remaining -= 1
            if self.fail_error is not None:
                raise self.fail_error
        return AIResponse(
            provider="mock",
            model="mock",
            content=f"Result for {agent_id}.\n- Finding A\n- Finding B\nDeliverables:\n- Work Item",
        )


def _setup_plan(db, task_count: int = 2) -> tuple[int, list[int]]:
    plan = Plan(
        title="Reliability Plan",
        objective="Verify reliability edge cases",
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
            title=f"Reliability Task {i}",
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


def test_concurrent_worker_claim_is_atomic() -> None:
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        # Two workers trying to claim the same pending workflow
        with SessionLocal() as db1, SessionLocal() as db2:
            claim1 = orch.claim_next(db1, "worker-alpha")
            claim2 = orch.claim_next(db2, "worker-beta")

            # Exactly one worker wins the claim
            assert (claim1 is not None and claim2 is None) or (claim1 is None and claim2 is not None)
            claimed = claim1 or claim2
            assert claimed.id == run_id
            assert claimed.lease_owner in ("worker-alpha", "worker-beta")
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_lease_expiration_and_recovery_by_another_worker() -> None:
    with SessionLocal() as db:
        plan_id, _ = _setup_plan(db, 1)
        orch = WorkflowOrchestrator(lease_seconds=1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        with SessionLocal() as db:
            w1_claim = orch.claim_next(db, "worker-1")
            assert w1_claim is not None
            assert w1_claim.lease_owner == "worker-1"

            # Simulate lease expiration in the past
            w1_claim.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
            db.commit()

        # Worker 2 attempts claim
        with SessionLocal() as db:
            w2_claim = orch.claim_next(db, "worker-2")
            assert w2_claim is not None
            assert w2_claim.id == run_id
            assert w2_claim.lease_owner == "worker-2"
            assert w2_claim.attempt_count == 2
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_worker_lost_lease_does_not_commit_results() -> None:
    agent = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=agent, lease_seconds=1)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    try:
        # Worker 1 claims
        with SessionLocal() as db:
            orch.claim_next(db, "worker-1")

        # Worker 2 steals lease because worker 1's lease expired
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            assert r is not None
            r.lease_owner = "worker-2"
            r.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=120)
            db.commit()

        # Worker 1 tries to process, but should detect lost lease and not complete workflow
        processed = await orch.process(run_id, "worker-1")
        assert processed.lease_owner == "worker-2"

        with SessionLocal() as db:
            current = db.get(WorkflowRun, run_id)
            assert current is not None
            # Workflow must NOT be marked completed by worker-1
            assert current.status != "completed"
            assert current.lease_owner == "worker-2"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_stale_running_execution_recovered_and_retried() -> None:
    agent = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

        # Simulate worker 1 crashing while executing task
        orch.claim_next(db, "crashed-worker")
        stale_exec = TaskExecution(
            task_id=task_id,
            workflow_run_id=run_id,
            agent_id="researcher",
            status="running",
            input_snapshot="Orphaned prompt",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        task = db.get(Task, task_id)
        assert task is not None
        task.status = "in_progress"
        db.add(stale_exec)
        # Expire worker lease
        r = db.get(WorkflowRun, run_id)
        assert r is not None
        r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
        stale_id = stale_exec.id

    try:
        # Recovering worker claims and processes
        with SessionLocal() as db:
            claimed = orch.claim_next(db, "recovering-worker")
            assert claimed is not None

        completed_run = await orch.process(run_id, "recovering-worker")
        assert completed_run.status == "completed"

        with SessionLocal() as db:
            stale_row = db.get(TaskExecution, stale_id)
            assert stale_row is not None
            assert stale_row.status == "failed"
            assert stale_row.error_code == "INTERRUPTED_EXECUTION"

            # Check that there is now a completed attempt for this task
            success_row = db.scalar(
                select(TaskExecution)
                .where(
                    TaskExecution.task_id == task_id,
                    TaskExecution.workflow_run_id == run_id,
                    TaskExecution.status == "completed",
                )
            )
            assert success_row is not None
            assert success_row.id != stale_id
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_recovery_synthesizes_missing_handoff_after_crash_scenario_d() -> None:
    agent = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        t1_id, t2_id = task_ids

        # Worker 1 executed task 1, committed it, but crashed before creating handoff
        orch.claim_next(db, "worker-1")
        t1 = db.get(Task, t1_id)
        assert t1 is not None
        t1.status = "done"
        exec1 = TaskExecution(
            task_id=t1_id,
            workflow_run_id=run_id,
            agent_id="researcher",
            status="completed",
            input_snapshot="t1 prompt",
            output_content="Research summary\n- Finding 1\nDeliverables:\n- Spec",
            started_at=NOW - timedelta(minutes=5),
            completed_at=NOW - timedelta(minutes=4),
        )
        db.add(exec1)
        # Expire lease
        r = db.get(WorkflowRun, run_id)
        assert r is not None
        r.lease_expires_at = NOW - timedelta(seconds=1)
        r.completed_tasks = 1
        db.commit()

    try:
        # Worker 2 claims and resumes
        with SessionLocal() as db:
            w2 = orch.claim_next(db, "worker-2")
            assert w2 is not None

        completed = await orch.process(run_id, "worker-2")
        assert completed.status == "completed"

        with SessionLocal() as db:
            # Handoff must exist and have been received by Task 2
            handoff = db.scalar(
                select(AgentHandoff).where(
                    AgentHandoff.workflow_run_id == run_id,
                    AgentHandoff.target_task_id == t2_id,
                )
            )
            assert handoff is not None
            assert handoff.source_agent_id == "researcher"
            assert handoff.target_agent_id == "developer"

            exec2 = db.scalar(
                select(TaskExecution).where(
                    TaskExecution.task_id == t2_id,
                    TaskExecution.workflow_run_id == run_id,
                )
            )
            assert exec2 is not None
            assert "Structured Handoff from Researcher AI to Developer AI" in (exec2.input_snapshot or "")
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_concurrent_handoff_insert_is_idempotent() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run = WorkflowRun(plan_id=plan_id, status="running", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run)
        db.flush()
        t1 = db.get(Task, task_ids[0])
        t2 = db.get(Task, task_ids[1])
        assert t1 is not None and t2 is not None
        execution = TaskExecution(
            task_id=t1.id,
            workflow_run_id=run.id,
            agent_id="researcher",
            status="completed",
            input_snapshot="test",
            output_content="Summary output\n- Finding",
            started_at=NOW,
        )
        db.add(execution)
        db.commit()
        run_id = run.id
        exec_id = execution.id

    try:
        # Simulate two concurrent threads/workers creating handoff for same source & target
        with SessionLocal() as db1, SessionLocal() as db2:
            src1 = db1.get(Task, task_ids[0])
            tgt1 = db1.get(Task, task_ids[1])
            src2 = db2.get(Task, task_ids[0])
            tgt2 = db2.get(Task, task_ids[1])
            assert src1 is not None and tgt1 is not None and src2 is not None and tgt2 is not None

            h1 = create_agent_handoff(db1, run_id, exec_id, src1, tgt1)
            db1.commit()

            # Second call must not throw IntegrityError even if committed concurrently
            h2 = create_agent_handoff(db2, run_id, exec_id, src2, tgt2)
            db2.commit()

            assert h1 is not None and h2 is not None
            assert h1.id == h2.id

        with SessionLocal() as db:
            count = db.scalar(
                select(func.count(AgentHandoff.id)).where(
                    AgentHandoff.workflow_run_id == run_id,
                )
            )
            assert count == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_concurrent_artifact_creation_is_idempotent() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        run = WorkflowRun(plan_id=plan_id, status="completed", total_tasks=1, completed_tasks=1, idempotency_key=uuid4().hex, final_report="Report")
        db.add(run)
        db.flush()
        t1 = db.get(Task, task_ids[0])
        assert t1 is not None
        execution = TaskExecution(
            task_id=t1.id,
            workflow_run_id=run.id,
            agent_id="developer",
            status="completed",
            input_snapshot="test",
            output_content="code output",
            started_at=NOW,
        )
        db.add(execution)
        db.commit()
        exec_id = execution.id
        run_id = run.id

    try:
        with SessionLocal() as db1, SessionLocal() as db2:
            e1 = db1.get(TaskExecution, exec_id)
            task1 = db1.get(Task, task_ids[0])
            e2 = db2.get(TaskExecution, exec_id)
            task2 = db2.get(Task, task_ids[0])
            assert e1 is not None and task1 is not None and e2 is not None and task2 is not None

            a1 = create_execution_artifact(db1, e1, task1)
            db1.commit()

            a2 = create_execution_artifact(db2, e2, task2)
            db2.commit()

            assert a1 is not None and a2 is not None
            assert a1.id == a2.id

        with SessionLocal() as db:
            art_count = db.scalar(select(func.count(Artifact.id)).where(Artifact.task_execution_id == exec_id))
            assert art_count == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_cross_run_and_manual_handoff_rejection() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 2)
        run1 = WorkflowRun(plan_id=plan_id, status="completed", total_tasks=2, completed_tasks=2, idempotency_key=uuid4().hex)
        run2 = WorkflowRun(plan_id=plan_id, status="running", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add_all([run1, run2])
        db.commit()
        t1 = db.get(Task, task_ids[0])
        t2 = db.get(Task, task_ids[1])
        assert t1 is not None and t2 is not None

        # Manual execution (workflow_run_id is None)
        manual_exec = TaskExecution(task_id=t1.id, workflow_run_id=None, agent_id="researcher", status="completed", input_snapshot="m", output_content="Out", started_at=NOW)
        # Run 1 execution
        run1_exec = TaskExecution(task_id=t1.id, workflow_run_id=run1.id, agent_id="researcher", status="completed", input_snapshot="r1", output_content="Out", started_at=NOW)
        db.add_all([manual_exec, run1_exec])
        db.commit()
        manual_id = manual_exec.id
        run1_exec_id = run1_exec.id
        run1_id = run1.id
        run2_id = run2.id

    try:
        with SessionLocal() as db:
            src = db.get(Task, task_ids[0])
            tgt = db.get(Task, task_ids[1])
            assert src is not None and tgt is not None

            # Manual execution must NOT produce a workflow handoff
            h_manual = create_agent_handoff(db, run1_id, manual_id, src, tgt)
            assert h_manual is None

            # Execution from Run 1 cannot produce a handoff for Run 2
            h_cross = create_agent_handoff(db, run2_id, run1_exec_id, src, tgt)
            assert h_cross is None

            # Self handoff rejected
            h_self = create_agent_handoff(db, run1_id, run1_exec_id, src, src)
            assert h_self is None
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_transient_gemini_retry_succeeds_on_second_attempt() -> None:
    agent = ControlledAgentService()
    # First attempt fails with 429 Rate limit, then second attempt succeeds
    agent.fail_agent_id = "researcher"
    agent.fail_error = ApplicationError(429, "AI_RATE_LIMIT_EXCEEDED", "Rate limit exceeded; retry allowed.")
    agent.fail_attempts_remaining = 1

    exec_svc = TaskExecutionService(
        agent_service=agent,  # type: ignore[arg-type]
        max_ai_attempts=3,
        retry_base_seconds=0.01,
    )

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            execution = await exec_svc.execute(db, task_id)
            assert execution.status == "completed"
            assert agent.call_count["researcher"] == 2
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_permanent_gemini_error_fails_immediately_without_retry() -> None:
    agent = ControlledAgentService()
    agent.fail_agent_id = "researcher"
    agent.fail_error = ApplicationError(400, "AI_BAD_REQUEST", "Invalid parameters.")
    agent.fail_attempts_remaining = 5

    exec_svc = TaskExecutionService(
        agent_service=agent,  # type: ignore[arg-type]
        max_ai_attempts=3,
        retry_base_seconds=0.01,
    )

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        task_id = task_ids[0]

    try:
        with SessionLocal() as db:
            execution = await exec_svc.execute(db, task_id)
            assert execution.status == "failed"
            assert execution.error_code == "AI_BAD_REQUEST"
            # Exactly 1 call was made (no useless retries)
            assert agent.call_count["researcher"] == 1
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_cancellation_during_retry_aborts_promptly() -> None:
    agent = ControlledAgentService()
    agent.fail_agent_id = "researcher"
    agent.fail_error = ApplicationError(503, "AI_PROVIDER_ERROR", "Service unavailable.")
    agent.fail_attempts_remaining = 3

    exec_svc = TaskExecutionService(
        agent_service=agent,  # type: ignore[arg-type]
        max_ai_attempts=3,
        retry_base_seconds=10.0,
    )

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        task_id = task_ids[0]

    try:
        cancelled_flag = False

        def check_keep_alive() -> bool:
            return not cancelled_flag

        # Signal cancellation during wait
        async def cancel_soon():
            await asyncio.sleep(0.05)
            nonlocal cancelled_flag
            cancelled_flag = True

        asyncio.create_task(cancel_soon())

        with SessionLocal() as db:
            with pytest.raises(asyncio.CancelledError):
                await exec_svc.execute(db, task_id, keep_alive=check_keep_alive)

            # Execution must be cleanly marked cancelled
            execution = db.scalar(
                select(TaskExecution).where(TaskExecution.task_id == task_id)
            )
            assert execution is not None
            assert execution.status == "cancelled"
            assert execution.error_code == "EXECUTION_CANCELLED"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_cancel_workflow_aborts_running_executions_atomically() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch.claim_next(db, "worker-1")

        task = db.get(Task, task_ids[0])
        assert task is not None
        task.status = "in_progress"
        execution = TaskExecution(
            task_id=task.id,
            workflow_run_id=run.id,
            agent_id="researcher",
            status="running",
            input_snapshot="In flight",
            started_at=NOW,
        )
        db.add(execution)
        db.commit()
        run_id = run.id
        exec_id = execution.id

    try:
        with SessionLocal() as db:
            cancelled_run = cancel_workflow(db, run_id)
            assert cancelled_run.status == "cancelled"

            exec_row = db.get(TaskExecution, exec_id)
            assert exec_row is not None
            assert exec_row.status == "cancelled"
            assert exec_row.error_code == "EXECUTION_CANCELLED"

            task_row = db.get(Task, task_ids[0])
            assert task_row is not None
            assert task_row.status == "todo"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


def test_retry_budget_exhaustion_terminates_workflow_safely() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        orch = WorkflowOrchestrator()
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run.attempt_count = MAX_WORKFLOW_ATTEMPTS  # 5 attempts exhausted
        # Expire lease
        run.lease_expires_at = NOW - timedelta(seconds=10)
        db.commit()
        run_id = run.id

    try:
        with SessionLocal() as db:
            claimed = orch.claim_next(db, "any-worker")
            # Must NOT claim because budget is exhausted
            assert claimed is None

            exhausted_run = db.get(WorkflowRun, run_id)
            assert exhausted_run is not None
            assert exhausted_run.status == "failed"
            assert exhausted_run.error_code == "WORKFLOW_ATTEMPTS_EXHAUSTED"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_task_attempt_limit_fails_workflow() -> None:
    agent = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch.claim_next(db, "worker-1")
        task_id = task_ids[0]

        # Insert 3 failed attempts for this task in this run
        for i in range(MAX_TASK_EXECUTION_ATTEMPTS):
            db.add(TaskExecution(
                task_id=task_id,
                workflow_run_id=run.id,
                agent_id="researcher",
                status="failed",
                error_code="INTERRUPTED_EXECUTION",
                input_snapshot="test",
                started_at=NOW - timedelta(minutes=i + 1),
                completed_at=NOW - timedelta(minutes=i),
            ))
        db.commit()
        run_id = run.id

    try:
        completed_run = await orch.process(run_id, "worker-1")
        assert completed_run.status == "failed"
        assert completed_run.error_code == "TASK_ATTEMPTS_EXHAUSTED"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()


@pytest.mark.anyio
async def test_manager_finalization_recovery_scenario_f() -> None:
    agent = ControlledAgentService()
    exec_svc = TaskExecutionService(agent_service=agent)  # type: ignore[arg-type]
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=agent)  # type: ignore[arg-type]

    with SessionLocal() as db:
        plan_id, task_ids = _setup_plan(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        orch.claim_next(db, "worker-1")

        # Task 1 was completed
        t1 = db.get(Task, task_ids[0])
        assert t1 is not None
        t1.status = "done"
        db.add(TaskExecution(
            task_id=t1.id,
            workflow_run_id=run.id,
            agent_id="researcher",
            status="completed",
            input_snapshot="prompt",
            output_content="Done",
            started_at=NOW - timedelta(minutes=2),
            completed_at=NOW - timedelta(minutes=1),
        ))

        # Worker 1 was in finalization when it crashed
        r = db.get(WorkflowRun, run.id)
        assert r is not None
        r.completed_tasks = 1
        r.finalizing_at = NOW - timedelta(minutes=1)
        r.finalization_attempts = 1
        # Lease expired
        r.lease_expires_at = NOW - timedelta(seconds=5)
        db.commit()
        run_id = run.id

    try:
        # Worker 2 claims and finishes finalization
        with SessionLocal() as db:
            claimed = orch.claim_next(db, "worker-2")
            assert claimed is not None

        completed = await orch.process(run_id, "worker-2")
        assert completed.status == "completed"
        assert completed.final_report is not None
        assert "Result for manager" in completed.final_report

        with SessionLocal() as db:
            # Artifact was created cleanly
            art = db.scalar(select(Artifact).where(Artifact.workflow_run_id == run_id))
            assert art is not None
            assert art.artifact_type == "report"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Task).where(Task.plan_id == plan_id))
            db.execute(delete(Plan).where(Plan.id == plan_id))
            db.commit()
