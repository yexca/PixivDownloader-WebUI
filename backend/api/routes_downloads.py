from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.repositories.job_repository import JobRepository
from backend.schemas.downloads import (
    DownloadCreateRequest,
    DownloadCreateResponse,
    download_request_options,
    download_request_workflow_config,
)
from backend.services.workflow_run_service import WorkflowRunService

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadCreateResponse)
def create_download(
    request: DownloadCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_download_shortcut(
            source="download_api",
            title="Download artwork" if request.artwork_id else "Download artist",
            draft_id=f"download:{request.artwork_id or request.user_id}",
            config=download_request_workflow_config(request),
            user_id=request.user_id,
            artwork_id=request.artwork_id,
            force_rescan=request.force_rescan,
            retry_failed=request.retry_failed,
            options=download_request_options(request),
        )
    finally:
        service.close()
    queue.wake()
    job_id = run.items[0].job_ids[0]
    repository = JobRepository(db_path)
    try:
        job = repository.get_by_id(job_id)
    finally:
        repository.close()
    return DownloadCreateResponse(job_id=job_id, status=job.status if job else "queued")
