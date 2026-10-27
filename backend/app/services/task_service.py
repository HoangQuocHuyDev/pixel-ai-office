from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import default_agent_registry
from app.core.exceptions import ApplicationError
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskStatus, TaskUpdate


def _agent_id(value: str | None) -> str | None:
    return None if value is None else default_agent_registry.get(value).id


def get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise ApplicationError(404, "TASK_NOT_FOUND", f"Task {task_id} not found.")
    return task


def create_task(db: Session, payload: TaskCreate) -> Task:
    task = Task(**payload.model_dump(exclude={"assigned_agent_id"}), assigned_agent_id=_agent_id(payload.assigned_agent_id))
    if task.status == "done": task.completed_at = datetime.now(timezone.utc)
    try:
        db.add(task); db.commit(); db.refresh(task); return task
    except Exception: db.rollback(); raise


def list_tasks(db: Session, status: TaskStatus | None = None, assigned_agent_id: str | None = None, limit: int = 100, offset: int = 0) -> list[Task]:
    stmt = select(Task)
    if status is not None: stmt = stmt.where(Task.status == status)
    if assigned_agent_id is not None: stmt = stmt.where(Task.assigned_agent_id == _agent_id(assigned_agent_id))
    stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


def update_task_status(db: Session, task_id: int, status: TaskStatus) -> Task:
    task = get_task(db, task_id)
    task.status = status
    task.completed_at = datetime.now(timezone.utc) if status == "done" else None
    task.updated_at = datetime.now(timezone.utc)
    try: db.commit(); db.refresh(task); return task
    except Exception: db.rollback(); raise


def update_task(db: Session, task_id: int, payload: TaskUpdate) -> Task:
    task = get_task(db, task_id)
    changes = payload.model_dump(exclude_unset=True)
    if "assigned_agent_id" in changes: changes["assigned_agent_id"] = _agent_id(changes["assigned_agent_id"])
    status = changes.pop("status", None)
    for field, value in changes.items(): setattr(task, field, value)
    if status is not None:
        task.status = status
        task.completed_at = datetime.now(timezone.utc) if status == "done" else None
    task.updated_at = datetime.now(timezone.utc)
    try: db.commit(); db.refresh(task); return task
    except Exception: db.rollback(); raise


def delete_task(db: Session, task_id: int) -> None:
    task = get_task(db, task_id)
    try: db.delete(task); db.commit()
    except Exception: db.rollback(); raise
