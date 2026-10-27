from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.task_execution import TaskExecution
from app.schemas.task_execution import TaskExecutionResponse
from app.services.task_execution_service import TaskExecutionService, get_execution, list_executions

router = APIRouter(tags=["task-executions"])


def get_task_execution_service() -> TaskExecutionService:
    return TaskExecutionService()


@router.post("/tasks/{task_id}/execute", response_model=TaskExecutionResponse)
async def execute_task(task_id: int, db: Annotated[Session, Depends(get_db)], service: Annotated[TaskExecutionService, Depends(get_task_execution_service)]) -> TaskExecution:
    return await service.execute(db, task_id)


@router.get("/tasks/{task_id}/executions", response_model=list[TaskExecutionResponse])
def task_execution_history(task_id: int, db: Annotated[Session, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> list[TaskExecution]:
    return list_executions(db, task_id, limit, offset)


@router.get("/task-executions/{execution_id}", response_model=TaskExecutionResponse)
def task_execution_detail(execution_id: int, db: Annotated[Session, Depends(get_db)]) -> TaskExecution:
    return get_execution(db, execution_id)
