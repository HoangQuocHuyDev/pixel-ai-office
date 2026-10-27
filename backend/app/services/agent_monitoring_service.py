from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import default_agent_registry
from app.models.plan import Plan
from app.models.task import Task
from app.models.task_execution import TaskExecution
from app.models.workflow_run import WorkflowRun
from app.schemas.agent import (
    AgentExecutionResponse,
    AgentExecutionStatistics,
    AgentMonitoringResponse,
    AgentMonitoringSummary,
    AgentPublicResponse,
    AgentTaskReference,
    AgentTimelineEvent,
    AgentTimelineResponse,
    AgentWorkflowReference,
)
from app.services.agent_activity_service import list_agent_activities


def _duration(started_at: datetime, completed_at: datetime | None) -> float | None:
    if completed_at is None or completed_at < started_at:
        return None
    return (completed_at - started_at).total_seconds()


def _statistics(db: Session, agent_id: str) -> AgentExecutionStatistics:
    row = db.execute(select(
        func.count(TaskExecution.id),
        func.count(TaskExecution.id).filter(TaskExecution.status == "completed"),
        func.count(TaskExecution.id).filter(TaskExecution.status == "failed"),
        func.count(TaskExecution.id).filter(TaskExecution.status == "cancelled"),
        func.avg(func.extract("epoch", TaskExecution.completed_at - TaskExecution.started_at)).filter(
            TaskExecution.completed_at.is_not(None), TaskExecution.completed_at >= TaskExecution.started_at
        ),
        func.max(func.coalesce(TaskExecution.completed_at, TaskExecution.started_at)),
    ).where(TaskExecution.agent_id == agent_id)).one()
    total, completed, failed, cancelled, average, last_active = row
    finished = completed + failed + cancelled
    return AgentExecutionStatistics(
        total_executions=total, completed_executions=completed, failed_executions=failed,
        cancelled_executions=cancelled,
        success_rate=round(completed * 100 / finished, 1) if finished else None,
        average_duration_seconds=round(float(average), 2) if average is not None else None,
        last_active_at=last_active,
    )


def get_agent_monitoring(db: Session, agent_id: str) -> AgentMonitoringResponse:
    agent = default_agent_registry.get(agent_id)
    activity = next(item for item in list_agent_activities(db) if item.agent_id == agent_id)
    task = db.get(Task, activity.current_task_id) if activity.current_task_id else None
    workflow = db.get(WorkflowRun, activity.workflow_run_id) if activity.workflow_run_id else None
    plan = db.get(Plan, workflow.plan_id) if workflow else None
    executions = db.execute(
        select(TaskExecution, Task).join(Task, Task.id == TaskExecution.task_id)
        .where(TaskExecution.agent_id == agent_id)
        .order_by(TaskExecution.started_at.desc(), TaskExecution.id.desc()).limit(25)
    ).all()
    return AgentMonitoringResponse(
        agent=AgentPublicResponse.from_definition(agent), current_activity=activity,
        current_task=AgentTaskReference(id=task.id, title=task.title, status=task.status) if task else None,
        current_workflow=AgentWorkflowReference(
            id=workflow.id, plan_id=workflow.plan_id, plan_title=plan.title if plan else "Workflow",
            status=workflow.status,
        ) if workflow else None,
        statistics=_statistics(db, agent_id),
        recent_executions=[AgentExecutionResponse(
            id=execution.id, task_id=execution.task_id, task_title=execution_task.title,
            workflow_run_id=None, status=execution.status, started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=_duration(execution.started_at, execution.completed_at),
            output_content=execution.output_content, error_code=execution.error_code,
            error_message=execution.error_message,
        ) for execution, execution_task in executions],
    )


def get_monitoring_summary(db: Session) -> AgentMonitoringSummary:
    activities = list_agent_activities(db)
    counts = db.execute(select(
        func.count(TaskExecution.id),
        func.count(TaskExecution.id).filter(TaskExecution.status == "completed"),
        func.count(TaskExecution.id).filter(TaskExecution.status == "failed"),
    )).one()
    active_workflows = db.scalar(select(func.count(WorkflowRun.id)).where(WorkflowRun.status == "running")) or 0
    return AgentMonitoringSummary(
        total_agents=len(activities), working_agents=sum(a.status == "working" for a in activities),
        idle_agents=sum(a.status == "idle" for a in activities), failed_agents=sum(a.status == "failed" for a in activities),
        total_executions=counts[0], completed_executions=counts[1], failed_executions=counts[2],
        active_workflows=active_workflows,
    )


def get_agent_timeline(db: Session, agent_id: str, limit: int, offset: int) -> AgentTimelineResponse:
    default_agent_registry.get(agent_id)
    events: list[AgentTimelineEvent] = []
    executions = db.execute(
        select(TaskExecution, Task).join(Task, Task.id == TaskExecution.task_id)
        .where(TaskExecution.agent_id == agent_id)
    ).all()
    for execution, task in executions:
        events.append(AgentTimelineEvent(
            event_id=f"execution:{execution.id}:started", event_type="task_execution_started",
            agent_id=agent_id, task_id=task.id, execution_id=execution.id, status="running",
            timestamp=execution.started_at, description=f'Started task "{task.title}".',
        ))
        if execution.completed_at is not None and execution.status != "running":
            events.append(AgentTimelineEvent(
                event_id=f"execution:{execution.id}:{execution.status}", event_type=f"task_execution_{execution.status}",
                agent_id=agent_id, task_id=task.id, execution_id=execution.id, status=execution.status,
                timestamp=execution.completed_at, description=f'Task "{task.title}" {execution.status}.',
            ))
    if agent_id == "manager":
        workflows = db.execute(select(WorkflowRun, Plan).join(Plan, Plan.id == WorkflowRun.plan_id)).all()
        for workflow, plan in workflows:
            if workflow.status == "pending":
                continue
            events.append(AgentTimelineEvent(
                event_id=f"workflow:{workflow.id}:started", event_type="workflow_started", agent_id=agent_id,
                workflow_run_id=workflow.id, status="running", timestamp=workflow.started_at,
                description=f'Started workflow for "{plan.title}".',
            ))
            if workflow.completed_at is not None and workflow.status != "running":
                events.append(AgentTimelineEvent(
                    event_id=f"workflow:{workflow.id}:{workflow.status}", event_type=f"workflow_{workflow.status}",
                    agent_id=agent_id, workflow_run_id=workflow.id, status=workflow.status,
                    timestamp=workflow.completed_at, description=f'Workflow for "{plan.title}" {workflow.status}.',
                ))
                if workflow.status == "completed" and workflow.final_report is not None:
                    events.append(AgentTimelineEvent(
                        event_id=f"workflow:{workflow.id}:final-report", event_type="manager_final_report_completed",
                        agent_id=agent_id, workflow_run_id=workflow.id, status="completed",
                        timestamp=workflow.completed_at, description=f'Final report completed for "{plan.title}".',
                    ))
    events.sort(key=lambda event: (event.timestamp, event.event_id), reverse=True)
    return AgentTimelineResponse(items=events[offset:offset + limit], total=len(events), limit=limit, offset=offset)
