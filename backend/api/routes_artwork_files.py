from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.repositories.file_repository import ArtworkFileRepository
from backend.schemas.downloads import DownloadCreateResponse
from backend.schemas.files import ArtworkFileListResponse, artwork_file_response
from backend.services.job_service import JobService

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

    service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = service.create_download_job(
            user_id=None,
            artwork_id=file.artwork_id,
            retry_failed=True,
        )
    finally:
        service.close()
    queue.wake()
    return DownloadCreateResponse(job_id=job.id, status=job.status)
