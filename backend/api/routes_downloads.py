from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.downloads import (
    DownloadCreateRequest,
    DownloadCreateResponse,
)
from backend.services.shortcut_workflows import first_run_job_id, job_status, run_download_shortcut

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadCreateResponse)
def create_download(
    request: DownloadCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    run = run_download_shortcut(
        request,
        db_path=db_path,
        settings_json_path=settings_json_path,
        source="download_api",
    )
    queue.wake()
    job_id = first_run_job_id(run, db_path=db_path)
    return DownloadCreateResponse(job_id=job_id or run.id, status=job_status(db_path, job_id))
