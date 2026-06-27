from __future__ import annotations

from fastapi import APIRouter

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.downloads import DownloadCreateRequest, DownloadCreateResponse
from backend.services.job_service import JobService

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadCreateResponse)
def create_download(
    request: DownloadCreateRequest,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.create_download_job(
            user_id=request.user_id,
            artwork_id=request.artwork_id,
            force_rescan=request.force_rescan,
            retry_failed=request.retry_failed,
            options={
                "full_download": request.full_download,
                "max_artworks": request.max_artworks,
                "min_artwork_id": request.min_artwork_id.strip()
                if request.min_artwork_id
                else None,
                "max_artwork_id": request.max_artwork_id.strip()
                if request.max_artwork_id
                else None,
                "naming_rule": request.naming_rule.strip() if request.naming_rule else None,
                "only_new_artworks": request.only_new_artworks,
                "stop_if_artwork_count_above": request.stop_if_artwork_count_above,
                "naming_tag_variants": request.naming_tag_variants or [],
            },
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)
