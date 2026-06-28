from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.imports import LegacyDatabaseImportResponse
from backend.services.job_service import JobService
from backend.services.legacy_import_service import LegacyDatabaseImportService

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/legacy-database", response_model=LegacyDatabaseImportResponse)
def import_legacy_database(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
    file: Annotated[UploadFile, File()],
) -> LegacyDatabaseImportResponse:
    try:
        summary = LegacyDatabaseImportService(db_path).import_file(file.file)
    finally:
        file.file.close()
    job_service = JobService(db_path, settings_json_path=settings_json_path)
    try:
        job = job_service.create_legacy_import_hydration_job(
            artist_ids=summary.imported_artist_ids,
            legacy_latest_download_id_by_artist=summary.legacy_latest_download_id_by_artist or {},
        )
    finally:
        job_service.close()
    if job is not None:
        queue.wake()
    return LegacyDatabaseImportResponse(
        imported_artists=summary.imported_artists,
        skipped_rows=summary.skipped_rows,
        total_rows=summary.total_rows,
        hydration_job_id=job.id if job is not None else None,
        message=f"Imported {summary.imported_artists} artists from legacy database.",
    )
