from collections import defaultdict
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.agents.registry import default_agent_registry
from app.core.exceptions import ApplicationError
from app.models.agent_handoff import AgentHandoff
from app.models.artifact import Artifact
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import (
    WorkflowArtifactReference, WorkflowExecutionAttempt, WorkflowFinalization,
    WorkflowHandoffResponse, WorkflowPlanMetadata, WorkflowProgressSummary,
    WorkflowTimelineResponse, WorkflowTimelineStep,
)
from app.services.workflow_orchestrator import (
    check_retry_eligibility,
    get_retry_ancestor_ids,
    get_retry_run_ids,
    get_workflow_failure_info,
    resolve_reusable_completed_tasks_for_ancestors,
)

RESULT_PREVIEW_CHARS = 2_000
REPORT_PREVIEW_CHARS = 5_000


def _duration(started: datetime, completed: datetime | None) -> float | None:
    if completed is None or completed < started: return None
    return round((completed - started).total_seconds(), 2)


def _artifact_reference(artifact: Artifact) -> WorkflowArtifactReference:
    return WorkflowArtifactReference(
        id=artifact.id, title=artifact.title, artifact_type=artifact.artifact_type,
        agent_id=artifact.agent_id, task_execution_id=artifact.task_execution_id,
        workflow_run_id=artifact.workflow_run_id, created_at=artifact.created_at,
    )


def _agent_name(agent_id: str | None) -> str | None:
    if not agent_id:
        return None
    try:
        return default_agent_registry.get(agent_id).name
    except ApplicationError:
        return agent_id


def get_workflow_timeline(db: Session, workflow_id: int) -> WorkflowTimelineResponse:
    run = db.scalar(select(WorkflowRun).options(
        selectinload(WorkflowRun.plan).selectinload(Plan.tasks)
    ).where(WorkflowRun.id == workflow_id))
    if run is None: raise ApplicationError(404, "WORKFLOW_NOT_FOUND", f"Workflow {workflow_id} not found.")
    tasks = sorted(run.plan.tasks, key=lambda task: (task.sequence_order or 2_147_483_647, task.id))
    task_lookup = {task.id: task for task in tasks}
    executions = list(db.scalars(
        select(TaskExecution)
        .where(TaskExecution.workflow_run_id == run.id)
        .order_by(TaskExecution.task_id, TaskExecution.started_at, TaskExecution.id)
    ).all())
    execution_ids = [execution.id for execution in executions]

    handoffs_raw = list(db.scalars(
        select(AgentHandoff)
        .options(
            selectinload(AgentHandoff.source_execution),
            selectinload(AgentHandoff.target_task),
        )
        .where(AgentHandoff.workflow_run_id == run.id)
        .order_by(AgentHandoff.created_at, AgentHandoff.id)
    ).all())
    handoff_artifact_ids = {aid for h in handoffs_raw for aid in (h.artifact_ids or []) if isinstance(aid, int)}

    artifact_conditions = [Artifact.workflow_run_id == run.id]
    if execution_ids: artifact_conditions.append(Artifact.task_execution_id.in_(execution_ids))
    if handoff_artifact_ids: artifact_conditions.append(Artifact.id.in_(handoff_artifact_ids))
    artifacts = list(db.scalars(select(Artifact).where(or_(*artifact_conditions)).order_by(Artifact.created_at, Artifact.id)).all())
    artifacts_by_id = {artifact.id: artifact for artifact in artifacts}
    artifacts_by_execution: dict[int, list[Artifact]] = defaultdict(list)
    workflow_artifacts: list[Artifact] = []
    seen_artifact_ids: set[int] = set()
    for artifact in artifacts:
        if artifact.id in seen_artifact_ids: continue
        seen_artifact_ids.add(artifact.id)
        if artifact.task_execution_id is not None: artifacts_by_execution[artifact.task_execution_id].append(artifact)
        if artifact.workflow_run_id == run.id: workflow_artifacts.append(artifact)
    executions_by_task: dict[int, list[TaskExecution]] = defaultdict(list)
    for execution in executions: executions_by_task[execution.task_id].append(execution)

    try:
        ancestor_ids = get_retry_ancestor_ids(db, run.id)
    except ApplicationError:
        ancestor_ids = []
    reusable = resolve_reusable_completed_tasks_for_ancestors(db, run.plan.id, ancestor_ids)

    steps: list[WorkflowTimelineStep] = []
    for index, task in enumerate(tasks, start=1):
        task_executions = executions_by_task[task.id]
        attempts: list[WorkflowExecutionAttempt] = []
        for attempt_number, execution in enumerate(task_executions, start=1):
            output = execution.output_content
            attempts.append(WorkflowExecutionAttempt(
                id=execution.id, attempt_number=attempt_number, status=execution.status,
                started_at=execution.started_at, completed_at=execution.completed_at,
                duration_seconds=_duration(execution.started_at, execution.completed_at),
                result_preview=output[:RESULT_PREVIEW_CHARS] if output else None,
                result_truncated=bool(output and len(output) > RESULT_PREVIEW_CHARS),
                error_code=execution.error_code, error_message=execution.error_message,
                artifacts=[_artifact_reference(item) for item in artifacts_by_execution[execution.id]],
            ))
        latest = task_executions[-1] if task_executions else None
        pre_existing = False
        reused_from_run_id = None
        reused_execution_id = None
        if latest is not None:
            step_status = latest.status
            started_at = latest.started_at
            completed_at = latest.completed_at
        elif task.id in reusable:
            anc_exec = reusable[task.id]
            step_status = "completed"
            started_at = anc_exec.started_at
            completed_at = anc_exec.completed_at
            pre_existing = True
            reused_from_run_id = anc_exec.workflow_run_id
            reused_execution_id = anc_exec.id
        elif run.retried_from_run_id is None and task.status == "done":
            step_status = "completed"; started_at = None; completed_at = task.completed_at; pre_existing = True
        elif task.status == "cancelled":
            step_status = "cancelled"; started_at = None; completed_at = task.completed_at
        else:
            step_status = "pending"; started_at = None; completed_at = None
        try: agent_name = default_agent_registry.get(task.assigned_agent_id).name if task.assigned_agent_id else None
        except ApplicationError: agent_name = task.assigned_agent_id
        steps.append(WorkflowTimelineStep(
            step_number=task.sequence_order or index, task_id=task.id, task_title=task.title,
            task_description=task.description, agent_id=task.assigned_agent_id, agent_name=agent_name,
            status=step_status, started_at=started_at, completed_at=completed_at,
            duration_seconds=_duration(started_at, completed_at) if started_at else None, attempts=attempts,
            pre_existing=pre_existing,
            reused_from_run_id=reused_from_run_id,
            reused_execution_id=reused_execution_id,
        ))
    counts = {status: sum(step.status == status for step in steps) for status in ("completed", "running", "pending", "failed", "cancelled")}
    total = len(steps); completed = counts["completed"]
    progress = WorkflowProgressSummary(
        total_tasks=total, completed_tasks=completed, running_tasks=counts["running"],
        pending_tasks=counts["pending"], failed_tasks=counts["failed"], cancelled_tasks=counts["cancelled"],
        progress_percentage=round(completed * 100 / total, 1) if total else 0.0,
    )
    if run.final_report is not None and run.status == "completed": final_status = "completed"
    elif run.finalizing_at is not None and run.status == "running": final_status = "running"
    elif run.error_code == "FINAL_REPORT_FAILED": final_status = "failed"
    elif run.status == "cancelled": final_status = "cancelled"
    elif total and completed == total and run.status == "running": final_status = "pending"
    else: final_status = "not_started"
    report = run.final_report
    finalization = WorkflowFinalization(
        status=final_status, started_at=run.finalizing_at,
        completed_at=run.completed_at if final_status == "completed" else None,
        report_preview=report[:REPORT_PREVIEW_CHARS] if report else None,
        report_truncated=bool(report and len(report) > REPORT_PREVIEW_CHARS),
        error_code=run.error_code if final_status == "failed" else None,
        error_message=run.error_message if final_status == "failed" else None,
        artifacts=[_artifact_reference(item) for item in workflow_artifacts],
    )

    timeline_handoffs: list[WorkflowHandoffResponse] = []
    for h in handoffs_raw:
        src_task_id = h.source_execution.task_id if h.source_execution else None
        src_task = task_lookup.get(src_task_id) if src_task_id else None
        src_task_title = src_task.title if src_task else (f"Task {src_task_id}" if src_task_id else "Unknown Task")

        tgt_task = task_lookup.get(h.target_task_id) or h.target_task
        tgt_task_title = tgt_task.title if tgt_task else f"Task {h.target_task_id}"

        linked_artifacts = [
            _artifact_reference(artifacts_by_id[aid])
            for aid in (h.artifact_ids or [])
            if aid in artifacts_by_id
        ]

        timeline_handoffs.append(
            WorkflowHandoffResponse(
                id=h.id,
                workflow_run_id=h.workflow_run_id,
                source_task_execution_id=h.source_task_execution_id,
                source_task_id=src_task_id if src_task_id is not None else 0,
                source_task_title=src_task_title,
                source_agent_id=h.source_agent_id,
                source_agent_name=_agent_name(h.source_agent_id),
                target_task_id=h.target_task_id,
                target_task_title=tgt_task_title,
                target_agent_id=h.target_agent_id,
                target_agent_name=_agent_name(h.target_agent_id),
                summary=h.summary,
                key_findings=h.key_findings or [],
                deliverables=h.deliverables or [],
                next_steps=h.next_steps,
                artifacts=linked_artifacts,
                created_at=h.created_at,
            )
        )

    can_retry, retry_block_reason = check_retry_eligibility(db, run)
    failed_task_title, failed_task_id = get_workflow_failure_info(db, run)
    retry_run_ids = get_retry_run_ids(db, run.id)

    return WorkflowTimelineResponse(
        workflow_id=run.id, status=run.status,
        plan=WorkflowPlanMetadata(id=run.plan.id, title=run.plan.title, objective=run.plan.objective, status=run.plan.status, created_at=run.plan.created_at),
        started_at=run.started_at, completed_at=run.completed_at, updated_at=run.updated_at,
        progress=progress, steps=steps, handoffs=timeline_handoffs, finalization=finalization,
        error_code=run.error_code, error_message=run.error_message,
        execution_scope_note="Task executions are linked directly to this workflow run via verified workflow_run_id foreign keys.",
        can_retry=can_retry,
        retry_block_reason=retry_block_reason,
        retried_from_run_id=run.retried_from_run_id,
        retry_run_ids=retry_run_ids,
        failed_task_title=failed_task_title,
        failed_task_id=failed_task_id,
    )
