import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

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


class FakeAiService:
    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        if self.delay_seconds > 0:
            import asyncio
            await asyncio.sleep(self.delay_seconds)
        return AIResponse(provider="mock", model="mock", content=f"Output for {agent_id}")


def _create_plan_and_tasks(db, count: int = 2) -> tuple[int, list[int]]:
    plan = Plan(
        title="Concurrency Test Plan",
        objective="Verify PostgreSQL concurrent execution and lock handling",
        status="approved",
        idempotency_key=uuid4().hex,
        proposal_hash=uuid4().hex,
    )
    db.add(plan)
    db.flush()
    tasks = []
    agents = ["developer", "researcher"]
    for i in range(1, count + 1):
        t = Task(
            title=f"Concurrent Task {i}",
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


# 1. Two workers claim same pending run
def test_concurrency_two_workers_claim_same_pending_run() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id

    barrier = threading.Barrier(2)
    results: list[int | None] = [None, None]

    def worker_claim(idx: int, worker_id: str) -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            claimed = orch.claim_next(db, worker_id)
            results[idx] = claimed.id if claimed else None

    t1 = threading.Thread(target=worker_claim, args=(0, "worker-1"))
    t2 = threading.Thread(target=worker_claim, args=(1, "worker-2"))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        # Exactly ONE worker claimed the run; the other received None
        claims = [r for r in results if r is not None]
        assert len(claims) == 1
        assert claims[0] == run_id

        with SessionLocal() as db:
            updated_run = db.get(WorkflowRun, run_id)
            assert updated_run is not None
            assert updated_run.status == "running"
            assert updated_run.lease_owner in ("worker-1", "worker-2")
            assert updated_run.lease_generation == 1
    finally:
        _cleanup(plan_id)


# 2. Two workers reclaim expired lease
def test_concurrency_two_workers_reclaim_expired_lease() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        # Worker 0 claims first
        claimed = orch.claim_next(db, "worker-0")
        assert claimed is not None
        # Expire the lease
        claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()

    barrier = threading.Barrier(2)
    results: list[str | None] = [None, None]

    def reclaim(idx: int, worker_id: str) -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            r = orch.claim_next(db, worker_id)
            results[idx] = r.lease_owner if r else None

    t1 = threading.Thread(target=reclaim, args=(0, "reclaim-1"))
    t2 = threading.Thread(target=reclaim, args=(1, "reclaim-2"))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        successful = [r for r in results if r is not None]
        assert len(successful) == 1
        winner = successful[0]
        assert winner in ("reclaim-1", "reclaim-2")

        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            assert r.lease_owner == winner
            assert r.lease_generation == 2
    finally:
        _cleanup(plan_id)


# 3. Old worker completion vs new worker claim
def test_concurrency_old_worker_completion_vs_new_worker_claim() -> None:
    fake_ai = FakeAiService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]

        # Worker 1 claims (generation 1)
        claim1 = orch.claim_next(db, "worker-1")
        assert claim1.lease_generation == 1

        # Execution started under generation 1
        exec_record = TaskExecution(
            task_id=task_id,
            workflow_run_id=run_id,
            execution_lease_generation=1,
            agent_id="developer",
            status="running",
            input_snapshot="test snapshot",
            started_at=datetime.now(timezone.utc),
        )
        db.add(exec_record)
        db.commit()
        exec_id = exec_record.id

    try:
        # Worker 2 reclaims after lease expiry (generation becomes 2)
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            r.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            claim2 = orch.claim_next(db, "worker-2")
            assert claim2 is not None
            assert claim2.lease_generation == 2

        # Worker 1 tries to finalize its stale execution with generation 1
        with SessionLocal() as db:
            with pytest.raises(WorkflowFencingError):
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Late output from worker 1",
                    lease_generation=1,
                    worker_id="worker-1",
                    workflow_run_id=run_id,
                )

        # Confirm DB state is intact and not corrupted by worker 1
        with SessionLocal() as db:
            execution = db.get(TaskExecution, exec_id)
            assert execution.status == "running"  # Stale output was blocked!
    finally:
        _cleanup(plan_id)


# 4. Cancellation vs execution completion
def test_concurrency_cancellation_vs_execution_completion() -> None:
    fake_ai = FakeAiService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]
        claim = orch.claim_next(db, "worker-1")
        assert claim is not None

        exec_record = TaskExecution(
            task_id=task_id,
            workflow_run_id=run_id,
            execution_lease_generation=1,
            agent_id="developer",
            status="running",
            input_snapshot="test snapshot",
            started_at=datetime.now(timezone.utc),
        )
        db.add(exec_record)
        db.commit()
        exec_id = exec_record.id

    try:
        barrier = threading.Barrier(2)
        errors: list[Exception | None] = [None, None]

        def do_cancel() -> None:
            barrier.wait(timeout=5)
            try:
                with SessionLocal() as db:
                    cancel_workflow(db, run_id)
            except Exception as e:
                errors[0] = e

        def do_complete() -> None:
            barrier.wait(timeout=5)
            try:
                with SessionLocal() as db:
                    exec_svc._finish(
                        db,
                        exec_id,
                        output="Completed output",
                        lease_generation=1,
                        worker_id="worker-1",
                        workflow_run_id=run_id,
                    )
            except Exception as e:
                errors[1] = e

        t1 = threading.Thread(target=do_cancel)
        t2 = threading.Thread(target=do_complete)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            # Workflow must end up in a valid, immutable terminal state (cancelled)
            assert r.status == "cancelled"
            assert r.error_code == "WORKFLOW_CANCELLED"
    finally:
        _cleanup(plan_id)


# 5. Retry request vs retry request, same idempotency key
def test_concurrency_retry_same_idempotency_key() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Failed for concurrency test")

    shared_key = "concurrent-key-" + uuid4().hex
    barrier = threading.Barrier(2)
    retry_runs: list[int | None] = [None, None]
    exceptions: list[Exception | None] = [None, None]

    def do_retry(idx: int) -> None:
        barrier.wait(timeout=5)
        try:
            with SessionLocal() as db:
                new_run = orch.retry_workflow(db, run_id, idempotency_key=shared_key)
                retry_runs[idx] = new_run.id
        except Exception as e:
            exceptions[idx] = e

    t1 = threading.Thread(target=do_retry, args=(0,))
    t2 = threading.Thread(target=do_retry, args=(1,))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        # Both threads either get the exact same retry run, or one succeeded and one cleanly returned it
        valid_runs = [r for r in retry_runs if r is not None]
        assert len(valid_runs) >= 1
        if len(valid_runs) == 2:
            assert valid_runs[0] == valid_runs[1]
    finally:
        _cleanup(plan_id)


# 6. Retry request vs retry request, different keys
def test_concurrency_retry_different_keys_active_conflict() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Failed for concurrency test")

    key1 = "key-alpha-" + uuid4().hex
    key2 = "key-beta-" + uuid4().hex
    barrier = threading.Barrier(2)
    results: list[int | None] = [None, None]
    errors: list[ApplicationError | None] = [None, None]

    def try_retry(idx: int, key: str) -> None:
        barrier.wait(timeout=5)
        try:
            with SessionLocal() as db:
                r = orch.retry_workflow(db, run_id, idempotency_key=key)
                results[idx] = r.id
        except ApplicationError as e:
            errors[idx] = e

    t1 = threading.Thread(target=try_retry, args=(0, key1))
    t2 = threading.Thread(target=try_retry, args=(1, key2))
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        # Exactly one creates the active run; the other is rejected with WORKFLOW_ALREADY_ACTIVE
        successes = [r for r in results if r is not None]
        conflicts = [e for e in errors if e is not None and e.error_code == "WORKFLOW_ALREADY_ACTIVE"]
        assert len(successes) == 1
        assert len(conflicts) == 1
    finally:
        _cleanup(plan_id)


# 7. Retry request vs worker claim
def test_concurrency_retry_request_vs_worker_claim() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        orch._fail(db, run, "TASK_EXECUTION_FAILED", "Failed for test")

    barrier = threading.Barrier(2)
    retry_id: list[int | None] = [None]
    claim_id: list[int | None] = [None]

    def do_retry() -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            r = orch.retry_workflow(db, run_id)
            retry_id[0] = r.id

    def do_claim() -> None:
        barrier.wait(timeout=5)
        # Small yield to let retry insert or race
        time.sleep(0.01)
        with SessionLocal() as db:
            c = orch.claim_next(db, "claim-worker")
            claim_id[0] = c.id if c else None

    t1 = threading.Thread(target=do_retry)
    t2 = threading.Thread(target=do_claim)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        assert retry_id[0] is not None
        # If claim happened after retry, it claimed retry_id[0] or None; no crash
        if claim_id[0] is not None:
            assert claim_id[0] == retry_id[0]
    finally:
        _cleanup(plan_id)


# 8. Final report completion vs cancellation
def test_concurrency_final_report_vs_cancellation() -> None:
    fake_ai = FakeAiService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        claim = orch.claim_next(db, "worker-fin")
        assert claim is not None

        # Task done
        t = db.get(Task, task_ids[0])
        t.status = "done"
        db.add(TaskExecution(
            task_id=t.id, workflow_run_id=run_id, agent_id="developer",
            status="completed", input_snapshot="in", output_content="out",
            completed_at=datetime.now(timezone.utc),
        ))
        db.commit()

    barrier = threading.Barrier(2)

    def do_cancel() -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            cancel_workflow(db, run_id)

    def do_finalize() -> None:
        barrier.wait(timeout=5)
        import anyio
        anyio.run(orch.finalize_workflow, run_id, "worker-fin")

    t1 = threading.Thread(target=do_cancel)
    t2 = threading.Thread(target=do_finalize)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            # Must be terminal (completed or cancelled), no inconsistent intermediate state
            assert r.status in ("completed", "cancelled")
    finally:
        _cleanup(plan_id)


# 9. Heartbeat vs lease reclaim
def test_concurrency_heartbeat_vs_lease_reclaim() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        claim1 = orch.claim_next(db, "worker-heartbeat")
        assert claim1 is not None

        # Set lease to be exactly expired
        claim1.lease_expires_at = datetime.now(timezone.utc) - timedelta(milliseconds=10)
        db.commit()

    barrier = threading.Barrier(2)
    heartbeat_result: list[bool] = [False]
    reclaim_result: list[str | None] = [None]

    def do_heartbeat() -> None:
        barrier.wait(timeout=5)
        ok = orch._renew_lease(run_id, "worker-heartbeat", expected_generation=1)
        heartbeat_result[0] = ok

    def do_reclaim() -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            r = orch.claim_next(db, "worker-thief")
            reclaim_result[0] = r.lease_owner if r else None

    t1 = threading.Thread(target=do_heartbeat)
    t2 = threading.Thread(target=do_reclaim)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        with SessionLocal() as db:
            r = db.get(WorkflowRun, run_id)
            # Consistent ownership state: either heartbeat renewed or thief reclaimed
            assert r.lease_owner in ("worker-heartbeat", "worker-thief")
    finally:
        _cleanup(plan_id)


# 10. Task execution finish vs stale recovery
def test_concurrency_execution_finish_vs_stale_recovery() -> None:
    fake_ai = FakeAiService()
    exec_svc = TaskExecutionService(agent_service=fake_ai)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake_ai)

    with SessionLocal() as db:
        plan_id, task_ids = _create_plan_and_tasks(db, 1)
        run = orch.start_workflow(db, plan_id, uuid4().hex)
        run_id = run.id
        task_id = task_ids[0]
        claim = orch.claim_next(db, "worker-active")
        assert claim is not None

        exec_record = TaskExecution(
            task_id=task_id,
            workflow_run_id=run_id,
            execution_lease_generation=1,
            agent_id="developer",
            status="running",
            input_snapshot="snap",
            started_at=datetime.now(timezone.utc) - timedelta(seconds=200),
        )
        db.add(exec_record)
        t = db.get(Task, task_id)
        t.status = "in_progress"
        db.commit()
        exec_id = exec_record.id

    barrier = threading.Barrier(2)

    def do_recover() -> None:
        barrier.wait(timeout=5)
        with SessionLocal() as db:
            orch._recover_stale_workflow_executions(db, run_id)

    def do_finish() -> None:
        barrier.wait(timeout=5)
        try:
            with SessionLocal() as db:
                exec_svc._finish(
                    db,
                    exec_id,
                    output="Finished output",
                    lease_generation=1,
                    worker_id="worker-active",
                    workflow_run_id=run_id,
                )
        except Exception:
            pass

    t1 = threading.Thread(target=do_recover)
    t2 = threading.Thread(target=do_finish)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)

    try:
        with SessionLocal() as db:
            execution = db.get(TaskExecution, exec_id)
            assert execution.status in ("failed", "completed")
            t = db.get(Task, task_id)
            assert t.status in ("todo", "done")
    finally:
        _cleanup(plan_id)
