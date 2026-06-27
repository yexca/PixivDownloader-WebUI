from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.scheduled_tasks import scheduled_task_config_from_request
from backend.schemas.workflows import WorkflowRunRequest, WorkflowRunResponse
from backend.services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/run", response_model=WorkflowRunResponse)
def run_workflow(
    request: WorkflowRunRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> WorkflowRunResponse:
    service = ScheduledTaskService(db_path, settings_json_path=settings_json_path)
    try:
        jobs = service.run_config(scheduled_task_config_from_request(request.config))
    finally:
        service.close()
    if jobs:
        queue.wake()
    return WorkflowRunResponse(job_ids=[job.id for job in jobs], created=bool(jobs))
