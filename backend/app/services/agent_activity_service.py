from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import default_agent_registry
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.agent import AgentActivityResponse

RUNNING_FRESHNESS = timedelta(minutes=10)
FAILED_VISIBILITY = timedelta(seconds=30)


def list_agent_activities(db: Session, now: datetime | None = None) -> list[AgentActivityResponse]:
    current_time = now or datetime.now(timezone.utc)
    activities = {
        agent.id: AgentActivityResponse(agent_id=agent.id, status="idle", updated_at=current_time)
        for agent in default_agent_registry.list()
    }

    finalizing = db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.status == "running",
            WorkflowRun.finalizing_at.is_not(None),
            WorkflowRun.lease_expires_at > current_time,
        ).order_by(WorkflowRun.finalizing_at.desc(), WorkflowRun.id.desc()).limit(1)
    )
    if finalizing is not None:
        activities["manager"] = AgentActivityResponse(
            agent_id="manager", status="working", workflow_run_id=finalizing.id,
            activity_type="workflow_finalization", updated_at=finalizing.finalizing_at or current_time,
        )

    running_rows = db.execute(
        select(TaskExecution, Task).join(Task, Task.id == TaskExecution.task_id).where(
            TaskExecution.status == "running",
            TaskExecution.started_at >= current_time - RUNNING_FRESHNESS,
            TaskExecution.agent_id.in_(("developer", "researcher")),
        ).order_by(TaskExecution.started_at.desc(), TaskExecution.id.desc())
    ).all()
    selected: set[str] = set()
    for execution, task in running_rows:
        if execution.agent_id in selected:
            continue
        workflow_id = db.scalar(select(WorkflowRun.id).where(
            WorkflowRun.current_task_id == task.id,
            WorkflowRun.status == "running",
            WorkflowRun.lease_expires_at > current_time,
        ).order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc()).limit(1))
        activities[execution.agent_id] = AgentActivityResponse(
            agent_id=execution.agent_id, status="working", current_task_id=task.id,
            current_task_title=task.title, workflow_run_id=workflow_id,
            activity_type="task_execution", updated_at=execution.started_at,
        )
        selected.add(execution.agent_id)

    failed_rows = db.execute(
        select(TaskExecution, Task).join(Task, Task.id == TaskExecution.task_id).where(
            TaskExecution.status == "failed",
            TaskExecution.completed_at >= current_time - FAILED_VISIBILITY,
            TaskExecution.agent_id.in_(("developer", "researcher")),
        ).order_by(TaskExecution.completed_at.desc(), TaskExecution.id.desc())
    ).all()
    for execution, task in failed_rows:
        if activities[execution.agent_id].status != "idle":
            continue
        activities[execution.agent_id] = AgentActivityResponse(
            agent_id=execution.agent_id, status="failed", current_task_id=task.id,
            current_task_title=task.title, activity_type="task_execution_failed",
            updated_at=execution.completed_at or execution.started_at,
        )

    if activities["manager"].status == "idle":
        failed_workflow = db.scalar(select(WorkflowRun).where(
            WorkflowRun.status == "failed",
            WorkflowRun.error_code == "FINAL_REPORT_FAILED",
            WorkflowRun.updated_at >= current_time - FAILED_VISIBILITY,
        ).order_by(WorkflowRun.updated_at.desc(), WorkflowRun.id.desc()).limit(1))
        if failed_workflow is not None:
            activities["manager"] = AgentActivityResponse(
                agent_id="manager", status="failed", workflow_run_id=failed_workflow.id,
                activity_type="workflow_finalization_failed", updated_at=failed_workflow.updated_at,
            )

    return [activities[agent.id] for agent in default_agent_registry.list()]
