from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api")


@router.get("/health")
def health(request: Request) -> JSONResponse:
    enabled = request.app.state.executors_enabled
    queue = request.app.state.job_queue
    scheduler = request.app.state.workflow_trigger_runner
    healthy = not enabled or (queue.healthy and scheduler.healthy)
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "version": "0.2.0",
            "executors": {
                "enabled": enabled,
                "queue": not enabled or queue.healthy,
                "scheduler": not enabled or scheduler.healthy,
            },
        },
    )
