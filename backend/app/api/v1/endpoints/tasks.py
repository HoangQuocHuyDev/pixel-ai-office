from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskResponse, TaskStatus, TaskStatusUpdate, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("", response_model=list[TaskResponse])
def list_tasks(db: Annotated[Session, Depends(get_db)], status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None, assigned_agent_id: Annotated[str | None, Query(max_length=50)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 100, offset: Annotated[int, Query(ge=0)] = 0) -> list[Task]:
    return task_service.list_tasks(db, status_filter, assigned_agent_id, limit, offset)

@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
def create_task(payload: TaskCreate, db: Annotated[Session, Depends(get_db)]) -> Task:
    return task_service.create_task(db, payload)

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Annotated[Session, Depends(get_db)]) -> Task:
    return task_service.get_task(db, task_id)

@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, payload: TaskUpdate, db: Annotated[Session, Depends(get_db)]) -> Task:
    return task_service.update_task(db, task_id, payload)

@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_status(task_id: int, payload: TaskStatusUpdate, db: Annotated[Session, Depends(get_db)]) -> Task:
    return task_service.update_task_status(db, task_id, payload.status)

@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    task_service.delete_task(db, task_id)
