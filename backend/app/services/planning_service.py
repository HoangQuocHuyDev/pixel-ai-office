import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from pydantic import ValidationError

from app.agents.registry import default_agent_registry
from app.core.exceptions import ApplicationError
from app.models.conversation import Conversation
from app.models.plan import Plan
from app.models.task import Task
from app.schemas.planning import PlanApproveRequest, PlanProposal
from app.services.ai_service import AIService

PLANNING_INSTRUCTION = """You are Manager AI (Trưởng phòng Điều hành) in Pixel AI Office, reporting to the Director / CEO (Giám đốc / Sếp).
Your role is to analyze the Director's high-level goal, convert the objective into 1 to 10 concrete ordered tasks, and prepare an actionable plan for executive review.
Assign every task only to developer or researcher:
- researcher tasks: investigate requirements, gather information, survey technical solutions, or compare options.
- developer tasks: design architecture, write/refactor code, implement UI, build APIs/databases, or write automated tests.
Propose appropriate priority (low, medium, high) and logical sequence order.
Return only the provider-native structured response requested by the schema. Do not execute tasks, write SQL, claim work is complete, or assign work to manager."""


class PlanningService:
    def __init__(self, ai_service: AIService | None = None) -> None:
        self._ai_service = ai_service or AIService()

    async def generate(self, objective: str) -> PlanProposal:
        manager = default_agent_registry.get("manager")
        prompt = f"Create an actionable plan for this objective:\n\n{objective.strip()}"
        try:
            proposal = await self._ai_service.generate_structured(
                prompt,
                PlanProposal,
                f"{manager.system_instruction}\n\n{PLANNING_INSTRUCTION}",
            )
            return PlanProposal.model_validate(proposal)
        except ValidationError as exc:
            raise ApplicationError(502, "AI_INVALID_STRUCTURED_OUTPUT", "Manager AI returned an invalid plan.") from exc

    @staticmethod
    def _fingerprint(payload: PlanApproveRequest) -> str:
        canonical = payload.model_dump(mode="json", exclude={"idempotency_key"})
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def approve(self, db: Session, payload: PlanApproveRequest) -> Plan:
        fingerprint = self._fingerprint(payload)
        existing = db.scalar(select(Plan).options(selectinload(Plan.tasks)).where(Plan.idempotency_key == payload.idempotency_key))
        if existing is not None:
            if existing.proposal_hash != fingerprint:
                raise ApplicationError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency key was already used for a different plan.")
            return existing

        if payload.source_conversation_id is not None:
            conversation = db.get(Conversation, payload.source_conversation_id)
            if conversation is None:
                raise ApplicationError(404, "CONVERSATION_NOT_FOUND", "Source conversation was not found.")
            if conversation.agent_id != "manager":
                raise ApplicationError(422, "INVALID_SOURCE_CONVERSATION", "Planning source must be a Manager conversation.")

        for item in payload.proposal.tasks:
            default_agent_registry.get(item.assigned_agent_id)

        plan = Plan(
            title=payload.proposal.title,
            objective=payload.proposal.objective,
            status="approved",
            source_conversation_id=payload.source_conversation_id,
            idempotency_key=payload.idempotency_key,
            proposal_hash=fingerprint,
        )
        try:
            db.add(plan)
            db.flush()
            for item in payload.proposal.tasks:
                db.add(Task(
                    title=item.title,
                    description=item.description,
                    priority=item.priority,
                    assigned_agent_id=item.assigned_agent_id,
                    status="todo",
                    plan_id=plan.id,
                    sequence_order=item.sequence_order,
                ))
            db.commit()
            return get_plan(db, plan.id)
        except IntegrityError as exc:
            db.rollback()
            race_winner = db.scalar(select(Plan).options(selectinload(Plan.tasks)).where(Plan.idempotency_key == payload.idempotency_key))
            if race_winner is not None and race_winner.proposal_hash == fingerprint:
                return race_winner
            raise ApplicationError(409, "PLAN_APPROVAL_CONFLICT", "Plan approval conflicted with another request.") from exc
        except Exception:
            db.rollback()
            raise


def list_plans(db: Session, limit: int = 50, offset: int = 0) -> list[Plan]:
    statement = select(Plan).order_by(Plan.created_at.desc(), Plan.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


def get_plan(db: Session, plan_id: int) -> Plan:
    plan = db.scalar(select(Plan).options(selectinload(Plan.tasks)).where(Plan.id == plan_id))
    if plan is None:
        raise ApplicationError(404, "PLAN_NOT_FOUND", f"Plan {plan_id} not found.")
    return plan
