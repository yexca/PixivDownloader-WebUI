from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.domain.entities import ScheduledTaskConfig, ScheduledTaskTarget
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.schemas.downloads import DownloadCreateResponse
from backend.schemas.files import ArtworkFileListResponse, artwork_file_response
from backend.services.workflow_run_service import WorkflowRunService

router = APIRouter(tags=["artwork-files"])


@router.get("/api/artworks/{artwork_id}/files", response_model=ArtworkFileListResponse)
def list_artwork_files(artwork_id: str, db_path: DbPath) -> ArtworkFileListResponse:
    repository = ArtworkFileRepository(db_path)
    try:
        files = repository.list_by_artwork(artwork_id)
        return ArtworkFileListResponse(
            items=[artwork_file_response(file) for file in files],
            total=len(files),
        )
    finally:
        repository.close()


@router.post("/api/artwork-files/{file_id}/retry", response_model=DownloadCreateResponse)
def retry_artwork_file(
    file_id: int,
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
) -> DownloadCreateResponse:
    file_repository = ArtworkFileRepository(db_path)
    try:
        file = file_repository.get_by_id(file_id)
        if file is None:
            raise HTTPException(status_code=404, detail="artwork file not found")
    finally:
        file_repository.close()

    service = WorkflowRunService(db_path, settings_json_path=settings_json_path)
    try:
        run = service.run_download_shortcut(
            source="artwork_file_shortcut",
            title="Retry artwork file",
            draft_id=f"artwork-file-retry:{file_id}",
            config=ScheduledTaskConfig(
                target=ScheduledTaskTarget(type="single_artwork", artwork_id=file.artwork_id),
                actions=("download_artist",),
                max_artists_per_run=1,
            ),
            user_id=None,
            artwork_id=file.artwork_id,
            retry_failed=True,
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
