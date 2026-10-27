from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workflow_run import WorkflowRun
from app.schemas.workflow import WorkflowRetryRequest, WorkflowRunResponse, WorkflowStartRequest, WorkflowTimelineResponse
from app.services.workflow_orchestrator import (
    WorkflowOrchestrator,
    cancel_workflow,
    get_workflow,
    list_workflows,
    serialize_workflow_run,
)
from app.services.workflow_timeline_service import get_workflow_timeline

router = APIRouter(tags=["workflows"])


def get_workflow_orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator()


@router.post("/plans/{plan_id}/workflows", response_model=WorkflowRunResponse, status_code=status.HTTP_202_ACCEPTED)
def start_workflow(plan_id: int, payload: WorkflowStartRequest, db: Annotated[Session, Depends(get_db)], orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)]) -> WorkflowRunResponse:
    run = orchestrator.start_workflow(db, plan_id, payload.idempotency_key)
    return serialize_workflow_run(db, run)


@router.get("/plans/{plan_id}/workflows", response_model=list[WorkflowRunResponse])
def workflow_history(plan_id: int, db: Annotated[Session, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> list[WorkflowRunResponse]:
    runs = list_workflows(db, plan_id, limit, offset)
    return [serialize_workflow_run(db, r) for r in runs]


@router.get("/workflows/{workflow_run_id}", response_model=WorkflowRunResponse)
def workflow_status(workflow_run_id: int, db: Annotated[Session, Depends(get_db)]) -> WorkflowRunResponse:
    run = get_workflow(db, workflow_run_id)
    return serialize_workflow_run(db, run)


@router.get("/workflows/{workflow_run_id}/timeline", response_model=WorkflowTimelineResponse)
def workflow_timeline(workflow_run_id: int, db: Annotated[Session, Depends(get_db)]) -> WorkflowTimelineResponse:
    return get_workflow_timeline(db, workflow_run_id)


@router.post("/workflows/{workflow_run_id}/cancel", response_model=WorkflowRunResponse)
def cancel(workflow_run_id: int, db: Annotated[Session, Depends(get_db)]) -> WorkflowRunResponse:
    run = cancel_workflow(db, workflow_run_id)
    return serialize_workflow_run(db, run)


@router.post("/workflows/{workflow_run_id}/retry", response_model=WorkflowRunResponse, status_code=status.HTTP_202_ACCEPTED)
def retry(workflow_run_id: int, payload: WorkflowRetryRequest, db: Annotated[Session, Depends(get_db)], orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)]) -> WorkflowRunResponse:
    new_run = orchestrator.retry_workflow(db, workflow_run_id, payload.idempotency_key)
    return serialize_workflow_run(db, new_run)
