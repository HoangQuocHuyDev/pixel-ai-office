import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError, WorkflowFencingError
from app.db.session import SessionLocal
from app.models.agent_handoff import AgentHandoff
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import WorkflowRunResponse
from app.services.agent_service import AgentService
from app.services.artifact_service import create_workflow_artifact
from app.services.handoff_service import create_agent_handoff, format_handoff_for_context
from app.services.task_execution_service import TaskExecutionService

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")
MAX_WORKFLOW_ATTEMPTS = 5
MAX_TASK_EXECUTION_ATTEMPTS = 3
MAX_FINALIZATION_ATTEMPTS = 3

NON_RETRYABLE_ERROR_CODES = {
    "AI_AUTHENTICATION_ERROR",
    "AI_PERMISSION_DENIED",
    "AI_CONFIG_ERROR",
    "AI_MODEL_NOT_FOUND",
    "AI_BAD_REQUEST",
    "AI_INVALID_STRUCTURED_OUTPUT",
    "PLAN_NOT_FOUND",
    "PLAN_NOT_APPROVED",
    "PLAN_HAS_NO_TASKS",
    "PLAN_TASKS_INVALID",
    "PLAN_TASK_AGENT_INVALID",
    "WORKFLOW_PLAN_MISMATCH",
    "TASK_NOT_FOUND",
    "TASK_CANCELLED",
    "TASK_AGENT_REQUIRED",
    "TASK_AGENT_NOT_EXECUTABLE",
}


def get_retry_ancestor_ids(db: Session, workflow_run_id: int, max_depth: int = 50) -> list[int]:
    ancestors: list[int] = []
    visited: set[int] = {workflow_run_id}
    current_run = db.get(WorkflowRun, workflow_run_id)
    if current_run is None:
        raise ApplicationError(404, "WORKFLOW_NOT_FOUND", f"Workflow {workflow_run_id} not found.")
    plan_id = current_run.plan_id
    curr = current_run

    depth = 0
    while curr.retried_from_run_id is not None:
        depth += 1
        if depth > max_depth:
            raise ApplicationError(422, "BROKEN_WORKFLOW_LINEAGE", f"Retry lineage exceeds maximum depth of {max_depth}.")
        parent_id = curr.retried_from_run_id
        if parent_id in visited:
            raise ApplicationError(422, "BROKEN_WORKFLOW_LINEAGE", "Cycle detected in workflow retry lineage.")
        parent = db.get(WorkflowRun, parent_id)
        if parent is None:
            raise ApplicationError(422, "BROKEN_WORKFLOW_LINEAGE", f"Ancestor workflow run {parent_id} not found.")
        if parent.plan_id != plan_id:
            raise ApplicationError(422, "BROKEN_WORKFLOW_LINEAGE", f"Ancestor workflow run {parent_id} belongs to plan {parent.plan_id}, expected {plan_id}.")
        ancestors.append(parent_id)
        visited.add(parent_id)
        curr = parent

    return ancestors


def resolve_reusable_completed_tasks_for_ancestors(db: Session, plan_id: int, ancestor_ids: list[int]) -> dict[int, TaskExecution]:
    if not ancestor_ids:
        return {}

    executions = list(db.scalars(
        select(TaskExecution)
        .join(Task, TaskExecution.task_id == Task.id)
        .where(
            TaskExecution.workflow_run_id.in_(ancestor_ids),
            TaskExecution.status == "completed",
            Task.plan_id == plan_id,
        )
        .order_by(TaskExecution.completed_at.desc(), TaskExecution.id.desc())
    ).all())

    reusable: dict[int, TaskExecution] = {}
    for execution in executions:
        if execution.task_id not in reusable:
            reusable[execution.task_id] = execution
    return reusable


def resolve_reusable_completed_tasks(db: Session, run: WorkflowRun) -> dict[int, TaskExecution]:
    if run.retried_from_run_id is None:
        return {}
    ancestor_ids = get_retry_ancestor_ids(db, run.id)
    return resolve_reusable_completed_tasks_for_ancestors(db, run.plan_id, ancestor_ids)


class WorkflowOrchestrator:
    def __init__(self, execution_service: TaskExecutionService | None = None, agent_service: AgentService | None = None, lease_seconds: int = 120) -> None:
        self._agent_service = agent_service or AgentService()
        self._execution_service = execution_service or TaskExecutionService(agent_service=self._agent_service)
        self._lease_seconds = lease_seconds
        self._active_generations: dict[tuple[int, str], int] = {}

    def start_workflow(self, db: Session, plan_id: int, idempotency_key: str) -> WorkflowRun:
        existing = db.scalar(select(WorkflowRun).options(selectinload(WorkflowRun.current_task)).where(WorkflowRun.idempotency_key == idempotency_key))
        if existing:
            if existing.plan_id != plan_id:
                raise ApplicationError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency key belongs to another plan.")
            return existing
        plan = db.scalar(select(Plan).options(selectinload(Plan.tasks)).where(Plan.id == plan_id).with_for_update())
        if plan is None:
            raise ApplicationError(404, "PLAN_NOT_FOUND", f"Plan {plan_id} not found.")
        if plan.status != "approved":
            raise ApplicationError(409, "PLAN_NOT_APPROVED", "Only approved plans can start workflows.")
        tasks = sorted(plan.tasks, key=lambda item: item.sequence_order or 0)
        if not tasks:
            raise ApplicationError(422, "PLAN_HAS_NO_TASKS", "Plan has no tasks to execute.")
        if any(task.plan_id != plan.id or task.sequence_order is None for task in tasks):
            raise ApplicationError(422, "PLAN_TASKS_INVALID", "Plan tasks must have a valid sequence order.")
        if any(task.assigned_agent_id not in {"developer", "researcher"} for task in tasks):
            raise ApplicationError(422, "PLAN_TASK_AGENT_INVALID", "Every workflow task must be assigned to Developer or Researcher.")
        if db.scalar(select(WorkflowRun.id).where(WorkflowRun.plan_id == plan_id, WorkflowRun.status.in_(ACTIVE_STATUSES))) is not None:
            raise ApplicationError(409, "WORKFLOW_ALREADY_ACTIVE", "Plan already has an active workflow.")
        run = WorkflowRun(plan_id=plan_id, status="pending", total_tasks=len(tasks), completed_tasks=sum(task.status == "done" for task in tasks), idempotency_key=idempotency_key)
        try:
            db.add(run); db.commit(); db.refresh(run); return run
        except IntegrityError as exc:
            db.rollback()
            raise ApplicationError(409, "WORKFLOW_ALREADY_ACTIVE", "Plan already has an active workflow.") from exc

    def retry_workflow(self, db: Session, workflow_run_id: int, idempotency_key: str | None = None) -> WorkflowRun:
        run = db.scalar(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.plan).selectinload(Plan.tasks))
            .where(WorkflowRun.id == workflow_run_id)
            .with_for_update()
        )
        if run is None:
            raise ApplicationError(404, "WORKFLOW_NOT_FOUND", f"Workflow {workflow_run_id} not found.")
        if run.status != "failed":
            raise ApplicationError(409, "WORKFLOW_NOT_FAILED", f"Only failed workflows can be retried. Current status is '{run.status}'.")

        if idempotency_key:
            existing = db.scalar(
                select(WorkflowRun)
                .options(selectinload(WorkflowRun.current_task))
                .where(WorkflowRun.idempotency_key == idempotency_key)
            )
            if existing:
                if existing.retried_from_run_id != run.id or existing.plan_id != run.plan_id:
                    raise ApplicationError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency key belongs to another workflow run.")
                return existing
        else:
            idempotency_key = uuid4().hex

        can_retry, reason = check_retry_eligibility(db, run)
        if not can_retry:
            if "active workflow run" in (reason or ""):
                raise ApplicationError(409, "WORKFLOW_ALREADY_ACTIVE", reason or "Plan already has an active workflow.")
            if "Broken retry lineage" in (reason or ""):
                raise ApplicationError(422, "BROKEN_WORKFLOW_LINEAGE", reason or "Workflow lineage is broken.")
            raise ApplicationError(422, "WORKFLOW_NON_RETRYABLE", reason or "Workflow cannot be retried.")

        # Lineage-based reusable tasks resolution
        ancestor_ids = [run.id] + get_retry_ancestor_ids(db, run.id)
        reusable = resolve_reusable_completed_tasks_for_ancestors(db, run.plan_id, ancestor_ids)

        plan = run.plan
        tasks = sorted(plan.tasks, key=lambda item: item.sequence_order or 0)
        now = datetime.now(timezone.utc)
        for task in tasks:
            if task.id in reusable:
                task.status = "done"
                task.completed_at = reusable[task.id].completed_at
                task.updated_at = now
            else:
                task.status = "todo"
                task.completed_at = None
                task.updated_at = now

        completed_count = len(reusable)
        new_run = WorkflowRun(
            plan_id=run.plan_id,
            status="pending",
            total_tasks=len(tasks),
            completed_tasks=completed_count,
            idempotency_key=idempotency_key,
            retried_from_run_id=run.id,
        )
        try:
            db.add(new_run)
            db.commit()
            db.refresh(new_run)
            return new_run
        except IntegrityError as exc:
            db.rollback()
            raise ApplicationError(409, "WORKFLOW_ALREADY_ACTIVE", "Plan already has an active workflow.") from exc

    def claim_next(self, db: Session, worker_id: str) -> WorkflowRun | None:
        now = datetime.now(timezone.utc)
        statement = select(WorkflowRun).where(
            or_(WorkflowRun.status == "pending", (WorkflowRun.status == "running") & or_(WorkflowRun.lease_expires_at.is_(None), WorkflowRun.lease_expires_at < now))
        ).order_by(WorkflowRun.started_at.asc(), WorkflowRun.id.asc()).with_for_update(skip_locked=True).limit(1)
        run = db.scalar(statement)
        if run is None:
            return None
        if run.attempt_count >= MAX_WORKFLOW_ATTEMPTS:
            self._fail(
                db, run, "WORKFLOW_ATTEMPTS_EXHAUSTED",
                f"Workflow reached maximum retry attempts ({MAX_WORKFLOW_ATTEMPTS}) due to repeated worker interruptions or failures.",
            )
            return None
        run.status = "running"
        run.finalizing_at = None
        run.lease_owner = worker_id
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        run.lease_generation += 1
        run.attempt_count += 1
        run.updated_at = now
        db.commit(); db.refresh(run)
        return run

    def _recover_stale_workflow_executions(self, db: Session, workflow_run_id: int) -> list[int]:
        now = datetime.now(timezone.utc)
        stale_executions = list(db.scalars(
            select(TaskExecution)
            .where(TaskExecution.workflow_run_id == workflow_run_id, TaskExecution.status == "running")
            .with_for_update()
        ).all())
        recovered_task_ids: list[int] = []
        for execution in stale_executions:
            execution.status = "failed"
            execution.error_code = "INTERRUPTED_EXECUTION"
            execution.error_message = "Execution was interrupted by worker crash or lease loss; recovered by workflow orchestrator."
            execution.completed_at = now
            task = db.get(Task, execution.task_id)
            if task is not None and task.status == "in_progress":
                task.status = "todo"
                task.updated_at = now
                recovered_task_ids.append(task.id)
        if stale_executions:
            db.commit()
        return recovered_task_ids

    def _heartbeat(self, db: Session, run: WorkflowRun, worker_id: str, expected_generation: int | None = None) -> None:
        if run.status != "running" or run.lease_owner != worker_id or (expected_generation is not None and run.lease_generation != expected_generation):
            raise ApplicationError(409, "WORKFLOW_LEASE_LOST", "Workflow lease is no longer owned by this worker.")
        now = datetime.now(timezone.utc)
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        run.updated_at = now
        db.commit()

    def _renew_lease(self, workflow_run_id: int, worker_id: str, expected_generation: int | None = None) -> bool:
        if expected_generation is None:
            expected_generation = self._active_generations.get((workflow_run_id, worker_id))
        with SessionLocal() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
            if run is None or run.status != "running" or run.lease_owner != worker_id or (expected_generation is not None and run.lease_generation != expected_generation):
                return False
            self._heartbeat(db, run, worker_id, expected_generation=expected_generation)
            return True

    def _context_for(
        self,
        db: Session,
        tasks: list[Task],
        current_order: int,
        workflow_run_id: int | None = None,
        target_task_id: int | None = None,
    ) -> str:
        ancestor_ids: list[int] = []
        if workflow_run_id is not None:
            ancestor_ids = get_retry_ancestor_ids(db, workflow_run_id)
        lineage_ids = ([workflow_run_id] if workflow_run_id else []) + ancestor_ids

        if workflow_run_id is not None and target_task_id is not None:
            found_handoff: AgentHandoff | None = None
            for r_id in lineage_ids:
                candidate = db.scalar(
                    select(AgentHandoff)
                    .where(
                        AgentHandoff.workflow_run_id == r_id,
                        AgentHandoff.target_task_id == target_task_id,
                    )
                    .order_by(AgentHandoff.id.desc())
                    .limit(1)
                )
                if candidate is not None:
                    source_exec = db.get(TaskExecution, candidate.source_task_execution_id)
                    if (
                        source_exec is not None
                        and source_exec.status == "completed"
                        and source_exec.workflow_run_id is not None
                        and source_exec.workflow_run_id in lineage_ids
                    ):
                        found_handoff = candidate
                        break

            if found_handoff is not None:
                source_exec = db.get(TaskExecution, found_handoff.source_task_execution_id)
                source_task = next((t for t in tasks if t.id == (source_exec.task_id if source_exec else None)), None)
                source_title = source_task.title if source_task else "Previous step"
                return format_handoff_for_context(found_handoff, source_title)

        parts: list[str] = []
        for task in tasks:
            if (task.sequence_order or 0) >= current_order:
                continue
            query = select(TaskExecution).where(
                TaskExecution.task_id == task.id,
                TaskExecution.status == "completed",
            )
            if workflow_run_id is not None:
                run_rec = db.get(WorkflowRun, workflow_run_id)
                if run_rec and run_rec.retried_from_run_id is not None:
                    query = query.where(TaskExecution.workflow_run_id.in_(lineage_ids))
                else:
                    query = query.where(
                        or_(
                            TaskExecution.workflow_run_id == workflow_run_id,
                            TaskExecution.workflow_run_id.is_(None),
                        )
                    )
            execution = db.scalar(
                query.order_by(TaskExecution.completed_at.desc(), TaskExecution.id.desc()).limit(1)
            )
            if execution and execution.output_content:
                parts.append(f"Task {task.sequence_order} - {task.title}:\n{execution.output_content[:1200]}")
        return "\n\n".join(parts)[-3000:]

    def _fail(self, db: Session, run: WorkflowRun, code: str, message: str) -> None:
        run.status = "failed"; run.error_code = code; run.error_message = message[:2000]
        run.completed_at = datetime.now(timezone.utc); run.lease_owner = None; run.lease_expires_at = None; run.current_task_id = None; run.finalizing_at = None
        db.commit()

    async def process(self, workflow_run_id: int, worker_id: str) -> WorkflowRun:
        with SessionLocal() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
            if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", "Workflow was not found.")
            if run.status == "cancelled" or run.lease_owner != worker_id or run.status != "running":
                return run
            current_generation = run.lease_generation
            self._active_generations[(workflow_run_id, worker_id)] = current_generation
            self._heartbeat(db, run, worker_id, expected_generation=current_generation)

        while True:
            with SessionLocal() as db:
                self._recover_stale_workflow_executions(db, workflow_run_id)
                run = db.scalar(select(WorkflowRun).options(selectinload(WorkflowRun.plan).selectinload(Plan.tasks)).where(WorkflowRun.id == workflow_run_id).with_for_update())
                if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", "Workflow was not found.")
                if run.status == "cancelled" or run.lease_owner != worker_id or run.lease_generation != current_generation or run.status != "running":
                    logger.warning("Worker %s lost ownership/generation of workflow %s", worker_id, workflow_run_id)
                    return run
                tasks = sorted(run.plan.tasks, key=lambda item: item.sequence_order or 0)
                current_completed_ids = set(
                    db.scalars(
                        select(TaskExecution.task_id)
                        .where(
                            TaskExecution.workflow_run_id == workflow_run_id,
                            TaskExecution.status == "completed",
                        )
                    ).all()
                )
                if run.retried_from_run_id is not None:
                    ancestor_ids = get_retry_ancestor_ids(db, workflow_run_id)
                    reusable = resolve_reusable_completed_tasks_for_ancestors(db, run.plan_id, ancestor_ids)
                    completed_task_ids = set(reusable.keys()) | current_completed_ids
                else:
                    ancestor_ids = []
                    reusable = {}
                    pre_existing = set(
                        db.scalars(
                            select(Task.id)
                            .join(TaskExecution, TaskExecution.task_id == Task.id)
                            .where(
                                Task.plan_id == run.plan_id,
                                Task.status == "done",
                                TaskExecution.status == "completed",
                            )
                        ).all()
                    )
                    completed_task_ids = pre_existing | current_completed_ids

                run.completed_tasks = len(completed_task_ids)
                next_task = next((task for task in tasks if task.id not in completed_task_ids), None)
                if next_task is None:
                    run.current_task_id = None; db.commit(); break

                # Check task attempt limit
                attempts_count = db.scalar(select(func.count(TaskExecution.id)).where(TaskExecution.workflow_run_id == workflow_run_id, TaskExecution.task_id == next_task.id))
                if (attempts_count or 0) >= MAX_TASK_EXECUTION_ATTEMPTS:
                    self._fail(db, run, "TASK_ATTEMPTS_EXHAUSTED", f"Task '{next_task.title}' reached maximum attempt limit ({MAX_TASK_EXECUTION_ATTEMPTS}).")
                    return run

                # Recovery check: Ensure handoff from latest completed task to next_task exists
                prev_done_task = next((t for t in reversed(tasks) if (t.sequence_order or 0) < (next_task.sequence_order or 0) and t.id in completed_task_ids), None)
                if prev_done_task is not None:
                    existing_handoff = db.scalar(
                        select(AgentHandoff.id).where(
                            AgentHandoff.workflow_run_id.in_([workflow_run_id] + ancestor_ids),
                            AgentHandoff.target_task_id == next_task.id,
                        ).limit(1)
                    )
                    if existing_handoff is None:
                        prev_exec = None
                        if prev_done_task.id in current_completed_ids:
                            prev_exec = db.scalar(
                                select(TaskExecution)
                                .where(
                                    TaskExecution.task_id == prev_done_task.id,
                                    TaskExecution.workflow_run_id == workflow_run_id,
                                    TaskExecution.status == "completed",
                                )
                                .order_by(TaskExecution.id.desc())
                                .limit(1)
                            )
                        elif prev_done_task.id in reusable:
                            prev_exec = reusable[prev_done_task.id]

                        if prev_exec is not None:
                            create_agent_handoff(db, workflow_run_id, prev_exec.id, prev_done_task, next_task)
                            db.commit()

                run.current_task_id = next_task.id
                context = self._context_for(db, tasks, next_task.sequence_order or 0, workflow_run_id=workflow_run_id, target_task_id=next_task.id)
                self._heartbeat(db, run, worker_id, expected_generation=current_generation)
                task_id = next_task.id

            with SessionLocal() as execution_db:
                try:
                    execution = await self._execution_service.execute(
                        execution_db,
                        task_id,
                        context,
                        keep_alive=lambda: self._renew_lease(workflow_run_id, worker_id),
                        workflow_run_id=workflow_run_id,
                        lease_generation=current_generation,
                        worker_id=worker_id,
                    )
                except WorkflowFencingError as exc:
                    logger.warning("Fencing rejected execution for worker %s on workflow %s: %s", worker_id, workflow_run_id, exc)
                    with SessionLocal() as db:
                        run = db.get(WorkflowRun, workflow_run_id)
                        return run if run is not None else None  # type: ignore[return-value]
                except asyncio.CancelledError:
                    with SessionLocal() as db:
                        run = db.get(WorkflowRun, workflow_run_id)
                        if run is not None and run.status == "cancelled":
                            return run
                    raise
                except ApplicationError as exc:
                    with SessionLocal() as db:
                        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
                        if run and run.status == "running" and run.lease_owner == worker_id and run.lease_generation == current_generation:
                            self._fail(db, run, exc.error_code, exc.message)
                        return run  # type: ignore[return-value]

            with SessionLocal() as db:
                run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
                if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", "Workflow was not found.")
                if run.status == "cancelled": return run
                if run.lease_owner != worker_id or run.lease_generation != current_generation or run.status != "running":
                    logger.warning("Worker %s lost lease for workflow %s", worker_id, workflow_run_id)
                    return run
                now = datetime.now(timezone.utc)
                if run.lease_expires_at is not None and run.lease_expires_at < now:
                    logger.warning("Worker %s lease expired for workflow %s", worker_id, workflow_run_id)
                    return run
                if execution.status != "completed":
                    self._fail(db, run, execution.error_code or "TASK_EXECUTION_FAILED", execution.error_message or "A workflow task failed.")
                    return run
                run.completed_tasks = len(completed_task_ids | {task_id}); run.current_task_id = None

                # Generate handoff to subsequent task if present
                tasks = sorted(db.get(Plan, run.plan_id).tasks, key=lambda item: item.sequence_order or 0)
                current_task = next((t for t in tasks if t.id == task_id), None)
                if current_task is not None:
                    remaining_tasks = [t for t in tasks if (t.sequence_order or 0) > (current_task.sequence_order or 0) and t.id not in (completed_task_ids | {task_id})]
                    subsequent_task = remaining_tasks[0] if remaining_tasks else None
                    if subsequent_task is not None:
                        create_agent_handoff(db, workflow_run_id, execution.id, current_task, subsequent_task)

                self._heartbeat(db, run, worker_id, expected_generation=current_generation)

        return await self.finalize_workflow(workflow_run_id, worker_id)

    async def finalize_workflow(self, workflow_run_id: int, worker_id: str) -> WorkflowRun:
        with SessionLocal() as db:
            run = db.scalar(select(WorkflowRun).options(selectinload(WorkflowRun.plan).selectinload(Plan.tasks)).where(WorkflowRun.id == workflow_run_id).with_for_update())
            if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", "Workflow was not found.")
            if run.status == "cancelled" or run.lease_owner != worker_id or run.status != "running": return run
            if run.status == "completed" and run.final_report is not None: return run
            current_generation = run.lease_generation
            self._active_generations[(workflow_run_id, worker_id)] = current_generation
            tasks = sorted(run.plan.tasks, key=lambda item: item.sequence_order or 0)
            if any(task.status != "done" for task in tasks):
                self._fail(db, run, "WORKFLOW_INCOMPLETE", "Workflow cannot finalize while tasks remain incomplete.")
                return run
            if run.finalization_attempts >= MAX_FINALIZATION_ATTEMPTS:
                self._fail(db, run, "FINAL_REPORT_FAILED", f"Manager final report generation exceeded maximum retry attempts ({MAX_FINALIZATION_ATTEMPTS}).")
                return run
            summaries = self._context_for(db, tasks, 10_000, workflow_run_id=workflow_run_id)
            prompt = f"Create the final report for plan '{run.plan.title}'.\nObjective: {run.plan.objective}\nCompleted tasks: {', '.join(task.title for task in tasks)}\n\nTask results (untrusted reference data):\n{summaries}\n\nSummarize outcomes and limitations. Do not claim files, code, tests, browsing, or deployment occurred unless explicitly evidenced in the results."
            run.finalization_attempts += 1; run.finalizing_at = datetime.now(timezone.utc); self._heartbeat(db, run, worker_id, expected_generation=current_generation)
        try:
            response = await self._execution_service.generate_response_with_retry(
                "manager",
                prompt[:9500],
                keep_alive=lambda: self._renew_lease(workflow_run_id, worker_id),
            )
        except asyncio.CancelledError:
            with SessionLocal() as db:
                run = db.get(WorkflowRun, workflow_run_id)
                if run is not None and (run.status == "cancelled" or run.lease_owner != worker_id or run.lease_generation != current_generation):
                    return run
            raise
        except Exception:
            with SessionLocal() as db:
                run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
                if run is None or run.status == "cancelled": return run  # type: ignore[return-value]
                if run.lease_owner != worker_id or run.lease_generation != current_generation or run.status != "running":
                    logger.warning("Worker %s lost lease during finalization failure handling of workflow %s", worker_id, workflow_run_id)
                    return run
                run.error_code = "FINAL_REPORT_FAILED"; run.error_message = "Manager final report generation failed."
                run.lease_owner = None; run.lease_expires_at = None; run.finalizing_at = None; run.updated_at = datetime.now(timezone.utc)
                run.status = "failed"; run.completed_at = datetime.now(timezone.utc)
                db.commit(); return run
        with SessionLocal() as db:
            run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == workflow_run_id).with_for_update())
            if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", "Workflow was not found.")
            if run.status == "cancelled": return run
            if run.lease_owner != worker_id or run.lease_generation != current_generation or run.status != "running":
                logger.warning("Worker %s lost lease during finalization of workflow %s", worker_id, workflow_run_id)
                return run
            now = datetime.now(timezone.utc)
            if run.lease_expires_at is not None and run.lease_expires_at < now:
                logger.warning("Worker %s lease expired during finalization of workflow %s", worker_id, workflow_run_id)
                return run
            if run.final_report is not None:
                return run
            run.final_report = response.content; run.status = "completed"; run.completed_at = now
            run.completed_tasks = run.total_tasks; run.current_task_id = None; run.error_code = None; run.error_message = None
            run.lease_owner = None; run.lease_expires_at = None; run.finalizing_at = None; run.updated_at = now
            plan = db.get(Plan, run.plan_id)
            if plan is None: raise ApplicationError(404, "PLAN_NOT_FOUND", "Workflow plan was not found.")
            create_workflow_artifact(db, run, plan)
            db.commit(); db.refresh(run); return run


def get_workflow(db: Session, workflow_run_id: int) -> WorkflowRun:
    run = db.scalar(select(WorkflowRun).options(selectinload(WorkflowRun.current_task)).where(WorkflowRun.id == workflow_run_id))
    if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", f"Workflow {workflow_run_id} not found.")
    return run


def list_workflows(db: Session, plan_id: int, limit: int = 50, offset: int = 0) -> list[WorkflowRun]:
    if db.get(Plan, plan_id) is None: raise ApplicationError(404, "PLAN_NOT_FOUND", f"Plan {plan_id} not found.")
    statement = select(WorkflowRun).options(selectinload(WorkflowRun.current_task)).where(WorkflowRun.plan_id == plan_id).order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


def cancel_workflow(db: Session, workflow_run_id: int) -> WorkflowRun:
    run = db.scalar(select(WorkflowRun).options(selectinload(WorkflowRun.current_task)).where(WorkflowRun.id == workflow_run_id).with_for_update())
    if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", f"Workflow {workflow_run_id} not found.")
    if run.status in TERMINAL_STATUSES: return run
    now = datetime.now(timezone.utc)
    run.status = "cancelled"; run.completed_at = now; run.error_code = "WORKFLOW_CANCELLED"; run.error_message = "Cancellation requested. An in-flight AI call may finish before the worker observes it."
    run.lease_owner = None; run.lease_expires_at = None; run.finalizing_at = None; run.updated_at = now

    # Atomically cancel any in-flight task executions for this workflow run
    running_executions = list(db.scalars(
        select(TaskExecution).where(TaskExecution.workflow_run_id == workflow_run_id, TaskExecution.status == "running").with_for_update()
    ).all())
    for execution in running_executions:
        execution.status = "cancelled"
        execution.error_code = "EXECUTION_CANCELLED"
        execution.error_message = "Execution cancelled because workflow was cancelled."
        execution.completed_at = now
        task = db.get(Task, execution.task_id)
        if task is not None and task.status == "in_progress":
            task.status = "todo"
            task.updated_at = now

    db.commit(); db.refresh(run); return run


def check_retry_eligibility(db: Session, run: WorkflowRun) -> tuple[bool, str | None]:
    if run.status != "failed":
        return False, f"Workflow in status '{run.status}' cannot be retried. Only failed workflows can be retried."
    if run.error_code in NON_RETRYABLE_ERROR_CODES:
        return False, f"Workflow failed with non-retryable error ({run.error_code}). Configuration or plan must be resolved first."
    plan = db.get(Plan, run.plan_id)
    if plan is None:
        return False, f"Plan {run.plan_id} was not found."
    if plan.status != "approved":
        return False, "Plan is no longer approved."
    active_run = db.scalar(
        select(WorkflowRun.id).where(
            WorkflowRun.plan_id == run.plan_id,
            WorkflowRun.status.in_(ACTIVE_STATUSES),
        )
    )
    if active_run is not None:
        return False, f"Plan currently has an active workflow run (#{active_run})."
    try:
        get_retry_ancestor_ids(db, run.id)
    except ApplicationError as exc:
        if exc.error_code == "BROKEN_WORKFLOW_LINEAGE":
            return False, f"Broken retry lineage: {exc.message}"
        raise
    return True, None


def get_workflow_failure_info(db: Session, run: WorkflowRun) -> tuple[str | None, int | None]:
    if run.status != "failed":
        return None, None
    if run.error_code == "FINAL_REPORT_FAILED":
        return "Manager Final Report", None
    failed_exec = db.scalar(
        select(TaskExecution)
        .where(TaskExecution.workflow_run_id == run.id, TaskExecution.status == "failed")
        .order_by(TaskExecution.id.desc())
        .limit(1)
    )
    if failed_exec:
        t = db.get(Task, failed_exec.task_id)
        return (t.title if t else None), failed_exec.task_id
    if run.current_task_id:
        t = db.get(Task, run.current_task_id)
        return (t.title if t else None), run.current_task_id
    return None, None


def get_retry_run_ids(db: Session, run_id: int) -> list[int]:
    return list(db.scalars(
        select(WorkflowRun.id)
        .where(WorkflowRun.retried_from_run_id == run_id)
        .order_by(WorkflowRun.id.asc())
    ).all())


def serialize_workflow_run(db: Session, run: WorkflowRun) -> WorkflowRunResponse:
    can_retry, block_reason = check_retry_eligibility(db, run)
    failed_title, failed_id = get_workflow_failure_info(db, run)
    retry_ids = get_retry_run_ids(db, run.id)
    return WorkflowRunResponse(
        id=run.id,
        plan_id=run.plan_id,
        status=run.status,  # type: ignore[arg-type]
        current_task_id=run.current_task_id,
        current_task_title=run.current_task_title,
        current_agent_id=run.current_agent_id,
        completed_tasks=run.completed_tasks,
        total_tasks=run.total_tasks,
        final_report=run.final_report,
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
        can_retry=can_retry,
        retry_block_reason=block_reason,
        retried_from_run_id=run.retried_from_run_id,
        retry_run_ids=retry_ids,
        failed_task_title=failed_title,
        failed_task_id=failed_id,
    )
