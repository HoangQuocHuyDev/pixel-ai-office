from fastapi import APIRouter

from app.api.v1.endpoints import agents, ai, artifacts, conversations, planning, system, task_executions, tasks, workflows

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(conversations.router)
api_v1_router.include_router(ai.router)
api_v1_router.include_router(agents.router)
api_v1_router.include_router(tasks.router)
api_v1_router.include_router(planning.router)
api_v1_router.include_router(task_executions.router)
api_v1_router.include_router(workflows.router)
api_v1_router.include_router(artifacts.router)
api_v1_router.include_router(system.router)
