from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.schemas.imports import LegacyDatabaseImportResponse
from backend.services.legacy_import_service import LegacyDatabaseImportService
from backend.services.workflow_run_service import LegacyWorkflowItemRunService

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
    workflow_service = LegacyWorkflowItemRunService(
        db_path,
        settings_json_path=settings_json_path,
    )
    try:
        run = workflow_service.run_legacy_import_hydration(
            artist_ids=summary.imported_artist_ids,
            legacy_latest_download_id_by_artist=summary.legacy_latest_download_id_by_artist or {},
        )
    finally:
        workflow_service.close()
    job_id = first_workflow_job_id(run)
    if job_id is not None:
        queue.wake()
    return LegacyDatabaseImportResponse(
        imported_artists=summary.imported_artists,
        skipped_rows=summary.skipped_rows,
        total_rows=summary.total_rows,
        hydration_job_id=job_id,
        message=f"Imported {summary.imported_artists} artists from legacy database.",
    )


def first_workflow_job_id(run: object) -> str | None:
    if run is None:
        return None
    node_runs = getattr(run, "node_runs", [])
    for node_run in node_runs:
        job_ids = getattr(node_run, "job_ids", [])
        if job_ids:
            return str(job_ids[0])
    items = getattr(run, "items", [])
    for item in items:
        job_ids = getattr(item, "job_ids", [])
        if job_ids:
            return str(job_ids[0])
    return None
