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
from app.services.handoff_service import create_agent_handoff
from app.services.task_execution_service import TaskExecutionService
from app.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    cancel_workflow,
    check_retry_eligibility,
    get_retry_ancestor_ids,
    get_retry_run_ids,
    resolve_reusable_completed_tasks,
    resolve_reusable_completed_tasks_for_ancestors,
)
from app.services.workflow_timeline_service import get_workflow_timeline


class ControlledFakeAgentService:
    def __init__(self, fail_task_id: int | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_task_id = fail_task_id

    async def generate_response(self, agent_id: str, prompt: str) -> AIResponse:
        self.calls.append((agent_id, prompt))
        if self.fail_task_id is not None and f"Task title: Task {self.fail_task_id}" in prompt:
            raise ApplicationError(500, "AI_EXECUTION_FAILED", f"Simulated failure on task {self.fail_task_id}")
        return AIResponse(
            provider="mock",
            model="mock-gemini",
            content=f"Result from {agent_id} for prompt snippet: {prompt[:30]}...\nDeliverables:\n- Work Item",
        )


def _create_test_plan(db, task_count: int = 3) -> tuple[int, list[int]]:
    plan = Plan(
        title="Retry Lineage Verification Plan",
        objective="Verify multi-generation provenance and lineage consistency",
        status="approved",
        idempotency_key=uuid4().hex,
        proposal_hash=uuid4().hex,
    )
    db.add(plan)
    db.flush()
    tasks = []
    agents = ["developer", "researcher", "developer", "researcher"]
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


def _cleanup_plan(plan_id: int) -> None:
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


# 1. test_retry_uses_valid_ancestor_completed_execution
@pytest.mark.anyio
async def test_retry_uses_valid_ancestor_completed_execution() -> None:
    fake = ControlledFakeAgentService(fail_task_id=2)
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 3)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        # Run 1 executes Task 1, then fails on Task 2
        with SessionLocal() as db:
            orch.claim_next(db, "worker-1")
        res1 = await orch.process(run1_id, "worker-1")
        assert res1.status == "failed"

        # Verify Task 1 was completed in Run 1
        with SessionLocal() as db:
            exec1 = db.scalar(
                select(TaskExecution).where(TaskExecution.workflow_run_id == run1_id, TaskExecution.task_id == task_ids[0])
            )
            assert exec1 is not None and exec1.status == "completed"

            # Retry Run 1
            run2 = orch.retry_workflow(db, run1_id)
            assert run2.retried_from_run_id == run1_id
            assert run2.completed_tasks == 1

            # Task 1 status should be done; Task 2 and 3 should be todo
            t1 = db.get(Task, task_ids[0])
            t2 = db.get(Task, task_ids[1])
            assert t1.status == "done"
            assert t2.status == "todo"

        # Process Run 2 with failure removed
        fake.fail_task_id = None
        fake.calls.clear()

        with SessionLocal() as db:
            orch.claim_next(db, "worker-2")
        res2 = await orch.process(run2.id, "worker-2")
        assert res2.status == "completed"

        # Task 1 was skipped in Run 2; only Task 2, Task 3, and Manager executed
        assert [agent for agent, _ in fake.calls] == ["researcher", "developer", "manager"]

        # Timeline verification
        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run2.id)
            assert timeline.steps[0].pre_existing is True
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[0].status == "completed"
            assert len(timeline.steps[0].attempts) == 0
    finally:
        _cleanup_plan(plan_id)


# 2. test_manual_done_task_is_not_reused
def test_manual_done_task_is_not_reused() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

        # Task 1 was marked done manually (workflow_run_id is None)
        t1 = db.get(Task, task_ids[0])
        t1.status = "done"
        db.add(TaskExecution(
            task_id=task_ids[0],
            workflow_run_id=None,
            agent_id="developer",
            status="completed",
            input_snapshot="manual",
            output_content="manual result",
            completed_at=datetime.now(timezone.utc),
        ))
        db.commit()

        # Run 1 fails
        orch._fail(db, run1, "TASK_EXECUTION_FAILED", "Failed on task 2")

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            # Manual execution is NOT reused
            assert run2.completed_tasks == 0

            t1 = db.get(Task, task_ids[0])
            assert t1.status == "todo"

            # Timeline for Run 2 shows step 0 as pending (not completed)
            timeline = get_workflow_timeline(db, run2.id)
            assert timeline.steps[0].reused_from_run_id is None
            assert timeline.steps[0].status == "pending"
    finally:
        _cleanup_plan(plan_id)


# 3. test_unrelated_workflow_done_task_is_not_reused
def test_unrelated_workflow_done_task_is_not_reused() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        # Create an unrelated workflow run
        unrelated_run = WorkflowRun(
            plan_id=plan_id,
            status="completed",
            total_tasks=2,
            completed_tasks=2,
            idempotency_key=uuid4().hex,
        )
        db.add(unrelated_run)
        db.flush()

        # Add execution under unrelated run
        db.add(TaskExecution(
            task_id=task_ids[0],
            workflow_run_id=unrelated_run.id,
            agent_id="developer",
            status="completed",
            input_snapshot="unrelated",
            output_content="unrelated result",
            completed_at=datetime.now(timezone.utc),
        ))

        # Create target run1 that is NOT connected to unrelated_run
        run1 = WorkflowRun(
            plan_id=plan_id,
            status="failed",
            total_tasks=2,
            completed_tasks=0,
            idempotency_key=uuid4().hex,
            error_code="TASK_EXECUTION_FAILED",
            error_message="Failure",
        )
        db.add(run1)
        db.commit()
        run1_id = run1.id

    try:
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            # Unrelated execution is NOT reused
            assert run2.completed_tasks == 0
            t1 = db.get(Task, task_ids[0])
            assert t1.status == "todo"
    finally:
        _cleanup_plan(plan_id)


# 4. test_retry_chain_3_generations
@pytest.mark.anyio
async def test_retry_chain_3_generations() -> None:
    # 3 tasks: Task 1, Task 2, Task 3
    # Run 1 fails on Task 2
    # Run 2 reuses Task 1, fails on Task 3
    # Run 3 reuses Task 1 (Run 1) and Task 2 (Run 2), completes Task 3!
    fake = ControlledFakeAgentService(fail_task_id=2)
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 3)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "w1")
        res1 = await orch.process(run1_id, "w1")
        assert res1.status == "failed"

        # Retry into Run 2: now make Task 3 fail instead of Task 2
        fake.fail_task_id = 3
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            assert run2.retried_from_run_id == run1_id
            assert run2.completed_tasks == 1
            run2_id = run2.id

        with SessionLocal() as db:
            orch.claim_next(db, "w2")
        res2 = await orch.process(run2_id, "w2")
        assert res2.status == "failed"

        # Retry into Run 3: clear failures, both Task 1 & Task 2 should be reused
        fake.fail_task_id = None
        with SessionLocal() as db:
            ancestors = get_retry_ancestor_ids(db, run2_id)
            assert ancestors == [run1_id]

            run3 = orch.retry_workflow(db, run2_id)
            assert run3.retried_from_run_id == run2_id
            assert run3.completed_tasks == 2

            ancestors3 = get_retry_ancestor_ids(db, run3.id)
            assert ancestors3 == [run2_id, run1_id]

            reusable3 = resolve_reusable_completed_tasks(db, run3)
            assert task_ids[0] in reusable3
            assert task_ids[1] in reusable3
            assert reusable3[task_ids[0]].workflow_run_id == run1_id
            assert reusable3[task_ids[1]].workflow_run_id == run2_id

            run3_id = run3.id

        fake.calls.clear()
        with SessionLocal() as db:
            orch.claim_next(db, "w3")
        res3 = await orch.process(run3_id, "w3")
        assert res3.status == "completed"

        # Only Task 3 and Manager executed in Run 3
        assert [agent for agent, _ in fake.calls] == ["developer", "manager"]

        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run3_id)
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[1].reused_from_run_id == run2_id
            assert timeline.steps[2].reused_from_run_id is None
            assert timeline.steps[2].status == "completed"
    finally:
        _cleanup_plan(plan_id)


# 5. test_retry_chain_4_generations
@pytest.mark.anyio
async def test_retry_chain_4_generations() -> None:
    # 4 generations: Run 1 -> Run 2 -> Run 3 -> Run 4 across 4 tasks
    fake = ControlledFakeAgentService(fail_task_id=2)
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 4)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        # Run 1 fails on task 2
        with SessionLocal() as db: orch.claim_next(db, "w1")
        await orch.process(run1_id, "w1")

        # Run 2 fails on task 3
        fake.fail_task_id = 3
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            orch.claim_next(db, "w2")
        await orch.process(run2_id, "w2")

        # Run 3 fails on task 4
        fake.fail_task_id = 4
        with SessionLocal() as db:
            run3 = orch.retry_workflow(db, run2_id)
            run3_id = run3.id
            orch.claim_next(db, "w3")
        await orch.process(run3_id, "w3")

        # Run 4 completes!
        fake.fail_task_id = None
        fake.calls.clear()
        with SessionLocal() as db:
            run4 = orch.retry_workflow(db, run3_id)
            run4_id = run4.id
            assert run4.completed_tasks == 3
            ancestors = get_retry_ancestor_ids(db, run4_id)
            assert ancestors == [run3_id, run2_id, run1_id]
            orch.claim_next(db, "w4")

        res4 = await orch.process(run4_id, "w4")
        assert res4.status == "completed"
        # Only Task 4 and Manager executed in Run 4
        assert [agent for agent, _ in fake.calls] == ["researcher", "manager"]

        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run4_id)
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[1].reused_from_run_id == run2_id
            assert timeline.steps[2].reused_from_run_id == run3_id
            assert timeline.steps[3].reused_from_run_id is None
            assert timeline.progress.completed_tasks == 4
    finally:
        _cleanup_plan(plan_id)


# 6. test_handoff_inherited_from_grandparent
def test_handoff_inherited_from_grandparent() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 3)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=3, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        exec1 = TaskExecution(
            task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer",
            status="completed", input_snapshot="in", output_content="grandparent output",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(exec1); db.flush()

        handoff1 = create_agent_handoff(
            db, run1.id, exec1.id, db.get(Task, task_ids[0]), db.get(Task, task_ids[1])
        )
        db.flush()

        run2 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=3, completed_tasks=1, idempotency_key=uuid4().hex, retried_from_run_id=run1.id)
        db.add(run2); db.flush()

        run3 = WorkflowRun(plan_id=plan_id, status="running", total_tasks=3, completed_tasks=1, idempotency_key=uuid4().hex, retried_from_run_id=run2.id)
        db.add(run3); db.commit()

        tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
        context = orch._context_for(db, tasks, 2, workflow_run_id=run3.id, target_task_id=task_ids[1])
        assert "grandparent output" in context or handoff1.summary in context
        assert "Structured Handoff" in context
    _cleanup_plan(plan_id)


# 7. test_invalid_handoff_source_rejected
def test_invalid_handoff_source_rejected() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=2, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        # Source execution is failed
        bad_exec = TaskExecution(
            task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer",
            status="failed", input_snapshot="in", error_code="ERR", error_message="Failed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(bad_exec); db.flush()

        handoff = AgentHandoff(
            workflow_run_id=run1.id,
            source_task_execution_id=bad_exec.id,
            source_agent_id="developer",
            target_task_id=task_ids[1],
            target_agent_id="researcher",
            summary="Corrupted handoff",
            key_findings=[],
            deliverables=[],
            artifact_ids=[],
        )
        db.add(handoff)

        run2 = WorkflowRun(plan_id=plan_id, status="running", total_tasks=2, completed_tasks=0, idempotency_key=uuid4().hex, retried_from_run_id=run1.id)
        db.add(run2); db.commit()

        tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
        context = orch._context_for(db, tasks, 2, workflow_run_id=run2.id, target_task_id=task_ids[1])
        # Corrupted handoff was discarded!
        assert "Corrupted handoff" not in context
    _cleanup_plan(plan_id)


# 8. test_missing_handoff_fallback_to_provenance_executions
def test_missing_handoff_fallback_to_provenance_executions() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        good_exec = TaskExecution(
            task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer",
            status="completed", input_snapshot="in", output_content="Verified provenance output content",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(good_exec); db.flush()

        run2 = WorkflowRun(plan_id=plan_id, status="running", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex, retried_from_run_id=run1.id)
        db.add(run2); db.commit()

        tasks = list(db.scalars(select(Task).where(Task.plan_id == plan_id).order_by(Task.sequence_order)).all())
        context = orch._context_for(db, tasks, 2, workflow_run_id=run2.id, target_task_id=task_ids[1])
        assert "Verified provenance output content" in context
    _cleanup_plan(plan_id)


# 9. test_duplicate_execution_not_double_counted
def test_duplicate_execution_not_double_counted() -> None:
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=2, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        # Two completed executions for task 1
        exec1 = TaskExecution(task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer", status="completed", input_snapshot="snap1", completed_at=datetime.now(timezone.utc))
        exec2 = TaskExecution(task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer", status="completed", input_snapshot="snap2", completed_at=datetime.now(timezone.utc) + timedelta(seconds=1))
        db.add_all([exec1, exec2]); db.commit()

        reusable = resolve_reusable_completed_tasks_for_ancestors(db, plan_id, [run1.id])
        assert len(reusable) == 1
        assert task_ids[0] in reusable
    _cleanup_plan(plan_id)


# 10. test_completed_tasks_provenance_consistency
def test_completed_tasks_provenance_consistency() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 3)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=3, completed_tasks=1, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        db.add(TaskExecution(task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer", status="completed", input_snapshot="snap", completed_at=datetime.now(timezone.utc)))
        db.commit()

        run2 = orch.retry_workflow(db, run1.id)
        assert run2.completed_tasks == 1
        assert run2.total_tasks == 3
    _cleanup_plan(plan_id)


# 11. test_task_status_mismatch_handling
def test_task_status_mismatch_handling() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=2, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        # Task marked "done" in database but execution was failed!
        t1 = db.get(Task, task_ids[0])
        t1.status = "done"
        db.add(TaskExecution(task_id=task_ids[0], workflow_run_id=run1.id, agent_id="developer", status="failed", input_snapshot="snap", completed_at=datetime.now(timezone.utc)))
        db.commit()

        run2 = orch.retry_workflow(db, run1.id)
        # Mismatch handled: task was not completed successfully, so reset to todo
        assert run2.completed_tasks == 0
        t1_after = db.get(Task, task_ids[0])
        assert t1_after.status == "todo"
    _cleanup_plan(plan_id)


# 12. test_retry_idempotency_key_exists_and_unique_in_db
def test_retry_idempotency_key_exists_and_unique_in_db() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_test_plan(db, 1)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.commit()

        key = "idem-key-" + uuid4().hex
        run2 = orch.retry_workflow(db, run1.id, idempotency_key=key)
        assert run2.idempotency_key == key

        # Same key returns the exact same retry run
        run2_again = orch.retry_workflow(db, run1.id, idempotency_key=key)
        assert run2_again.id == run2.id
    _cleanup_plan(plan_id)


# 13. test_same_key_duplicate_retry_request
def test_same_key_duplicate_retry_request() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_test_plan(db, 1)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.commit()

        key = "shared-key-" + uuid4().hex
        r1 = orch.retry_workflow(db, run1.id, idempotency_key=key)
        r2 = orch.retry_workflow(db, run1.id, idempotency_key=key)
        assert r1.id == r2.id
    _cleanup_plan(plan_id)


# 14. test_different_key_active_run_conflict
def test_different_key_active_run_conflict() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_test_plan(db, 1)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.commit()

        key1 = "key-one-" + uuid4().hex
        key2 = "key-two-" + uuid4().hex
        orch.retry_workflow(db, run1.id, idempotency_key=key1)

        # Different key while plan has active run raises 409 WORKFLOW_ALREADY_ACTIVE
        with pytest.raises(ApplicationError) as exc:
            orch.retry_workflow(db, run1.id, idempotency_key=key2)
        assert exc.value.error_code == "WORKFLOW_ALREADY_ACTIVE"
    _cleanup_plan(plan_id)


# 15. test_retry_after_previous_retry_failed
def test_retry_after_previous_retry_failed() -> None:
    orch = WorkflowOrchestrator()
    with SessionLocal() as db:
        plan_id, _ = _create_test_plan(db, 1)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.commit()

        run2 = orch.retry_workflow(db, run1.id)
        orch._fail(db, run2, "TASK_EXECUTION_FAILED", "Failed in run 2")

        # Now run2 is failed, can retry run2
        run3 = orch.retry_workflow(db, run2.id)
        assert run3.retried_from_run_id == run2.id
        assert get_retry_ancestor_ids(db, run3.id) == [run2.id, run1.id]
    _cleanup_plan(plan_id)


# 16. test_broken_lineage_detection_and_rejection
def test_broken_lineage_detection_and_rejection() -> None:
    with SessionLocal() as db:
        plan_id, _ = _create_test_plan(db, 1)
        run1 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run1); db.flush()

        run2 = WorkflowRun(plan_id=plan_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex, retried_from_run_id=run1.id)
        db.add(run2); db.commit()

        # Create cycle: run1 points to run2
        run1.retried_from_run_id = run2.id
        db.commit()

        with pytest.raises(ApplicationError) as exc:
            get_retry_ancestor_ids(db, run2.id)
        assert exc.value.error_code == "BROKEN_WORKFLOW_LINEAGE"
        assert "Cycle detected" in exc.value.message

        # Test non-existent ancestor via mock db
        class MissingParentDb:
            def get(self, model, ident):
                if ident == run2.id:
                    return run2
                return None

        with pytest.raises(ApplicationError) as exc2:
            get_retry_ancestor_ids(MissingParentDb(), run2.id)  # type: ignore[arg-type]
        assert exc2.value.error_code == "BROKEN_WORKFLOW_LINEAGE"
        assert "not found" in exc2.value.message
    _cleanup_plan(plan_id)


# 17. test_cross_plan_lineage_rejection
def test_cross_plan_lineage_rejection() -> None:
    with SessionLocal() as db:
        plan_a_id, _ = _create_test_plan(db, 1)
        plan_b_id, _ = _create_test_plan(db, 1)

        run_a = WorkflowRun(plan_id=plan_a_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex)
        db.add(run_a); db.flush()

        # Run B claims to retry Run A across plans
        run_b = WorkflowRun(plan_id=plan_b_id, status="failed", total_tasks=1, completed_tasks=0, idempotency_key=uuid4().hex, retried_from_run_id=run_a.id)
        db.add(run_b); db.commit()

        with pytest.raises(ApplicationError) as exc:
            get_retry_ancestor_ids(db, run_b.id)
        assert exc.value.error_code == "BROKEN_WORKFLOW_LINEAGE"
        assert "expected" in exc.value.message
    _cleanup_plan(plan_a_id)
    _cleanup_plan(plan_b_id)


# 18. test_cancellation_recovery_race
@pytest.mark.anyio
async def test_cancellation_recovery_race() -> None:
    fake = ControlledFakeAgentService()
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        with SessionLocal() as db:
            orch.claim_next(db, "worker-canceller")

        # Simulate cancellation during processing
        with SessionLocal() as db:
            cancel_workflow(db, run1_id)

        res = await orch.process(run1_id, "worker-canceller")
        assert res.status == "cancelled"
    finally:
        _cleanup_plan(plan_id)


# 19. test_final_report_includes_ancestor_results
@pytest.mark.anyio
async def test_final_report_includes_ancestor_results() -> None:
    fake = ControlledFakeAgentService(fail_task_id=2)
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 2)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        with SessionLocal() as db: orch.claim_next(db, "w1")
        await orch.process(run1_id, "w1")

        # Retry with clear failures
        fake.fail_task_id = None
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            orch.claim_next(db, "w2")

        fake.calls.clear()
        res2 = await orch.process(run2_id, "w2")
        assert res2.status == "completed"

        # Check prompt sent to Manager for final report
        manager_call = next((call for call in fake.calls if call[0] == "manager"), None)
        assert manager_call is not None
        # Manager prompt should include output from Task 1 (executed in Run 1)
        assert "Task 1" in manager_call[1]
    finally:
        _cleanup_plan(plan_id)


# 20. test_full_regression_zero_regressions
@pytest.mark.anyio
async def test_full_regression_zero_regressions() -> None:
    # Full end-to-end integration: 3 tasks, 2 retries, timeline check
    fake = ControlledFakeAgentService(fail_task_id=2)
    exec_svc = TaskExecutionService(agent_service=fake)
    orch = WorkflowOrchestrator(execution_service=exec_svc, agent_service=fake)

    with SessionLocal() as db:
        plan_id, task_ids = _create_test_plan(db, 3)
        run1 = orch.start_workflow(db, plan_id, uuid4().hex)
        run1_id = run1.id

    try:
        with SessionLocal() as db: orch.claim_next(db, "w1")
        res1 = await orch.process(run1_id, "w1")
        assert res1.status == "failed"

        # Retry Run 1 -> Run 2
        fake.fail_task_id = None
        with SessionLocal() as db:
            run2 = orch.retry_workflow(db, run1_id)
            run2_id = run2.id
            orch.claim_next(db, "w2")

        res2 = await orch.process(run2_id, "w2")
        assert res2.status == "completed"

        with SessionLocal() as db:
            timeline = get_workflow_timeline(db, run2_id)
            assert timeline.progress.completed_tasks == 3
            assert timeline.steps[0].reused_from_run_id == run1_id
            assert timeline.steps[0].status == "completed"
            assert timeline.steps[1].reused_from_run_id is None
            assert timeline.steps[1].status == "completed"
            assert timeline.steps[2].reused_from_run_id is None
            assert timeline.steps[2].status == "completed"
            assert timeline.finalization.status == "completed"
    finally:
        _cleanup_plan(plan_id)
