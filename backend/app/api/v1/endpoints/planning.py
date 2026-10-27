from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.plan import Plan
from app.schemas.planning import PlanApproveRequest, PlanGenerateRequest, PlanProposal, PlanResponse, PlanSummary
from app.services.planning_service import PlanningService, get_plan, list_plans

router = APIRouter(tags=["planning"])


def get_planning_service() -> PlanningService:
    return PlanningService()


@router.post("/planning/generate", response_model=PlanProposal)
async def generate_plan(payload: PlanGenerateRequest, service: Annotated[PlanningService, Depends(get_planning_service)]) -> PlanProposal:
    return await service.generate(payload.objective)


@router.post("/planning/approve", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def approve_plan(payload: PlanApproveRequest, db: Annotated[Session, Depends(get_db)], service: Annotated[PlanningService, Depends(get_planning_service)]) -> Plan:
    return service.approve(db, payload)


@router.get("/plans", response_model=list[PlanSummary])
def plans(db: Annotated[Session, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> list[Plan]:
    return list_plans(db, limit, offset)


@router.get("/plans/{plan_id}", response_model=PlanResponse)
def plan_detail(plan_id: int, db: Annotated[Session, Depends(get_db)]) -> Plan:
    return get_plan(db, plan_id)
