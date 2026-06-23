from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue
from backend.schemas.downloads import DownloadCreateRequest, DownloadCreateResponse
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadCreateResponse)
def create_download(
    request: DownloadCreateRequest,
    db_path: DbPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = JobService(db_path)
    try:
        job = service.create_download_job(
            user_id=request.user_id,
            artwork_id=request.artwork_id,
            force_rescan=request.force_rescan,
            retry_failed=request.retry_failed,
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)
