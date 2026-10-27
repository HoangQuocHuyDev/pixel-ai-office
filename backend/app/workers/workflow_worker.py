import argparse
import asyncio
import logging
import signal
import socket
from uuid import uuid4

from app.db.session import SessionLocal
from app.services.workflow_orchestrator import WorkflowOrchestrator

logger = logging.getLogger(__name__)


class WorkflowWorker:
    def __init__(self, worker_id: str | None = None, poll_seconds: float = 2.0, orchestrator: WorkflowOrchestrator | None = None) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid4().hex[:10]}"
        self.poll_seconds = poll_seconds
        self.orchestrator = orchestrator or WorkflowOrchestrator()
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    async def run_once(self) -> bool:
        with SessionLocal() as db:
            run = self.orchestrator.claim_next(db, self.worker_id)
            if run is None: return False
            run_id = run.id
        logger.info("Worker %s claimed workflow %s", self.worker_id, run_id)
        await self.orchestrator.process(run_id, self.worker_id)
        return True

    async def run(self, once: bool = False) -> None:
        logger.info("Workflow worker %s started", self.worker_id)
        while not self._stopping:
            claimed = await self.run_once()
            if once: break
            if not claimed:
                await asyncio.sleep(self.poll_seconds)
        logger.info("Workflow worker %s stopped", self.worker_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PostgreSQL-backed workflow worker.")
    parser.add_argument("--once", action="store_true", help="Claim at most one workflow and exit.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    worker = WorkflowWorker(poll_seconds=max(args.poll_seconds, .1))
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name): signal.signal(getattr(signal, name), lambda *_: worker.stop())
    asyncio.run(worker.run(once=args.once))


if __name__ == "__main__":
    main()
