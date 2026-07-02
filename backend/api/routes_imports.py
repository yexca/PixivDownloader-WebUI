from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile

from backend.api.dependencies import DbPath, Queue, SettingsJsonPath
from backend.core.paths import resources_dir
from backend.repositories.legacy_import_repository import LegacyImport, LegacyImportRepository
from backend.schemas.imports import LegacyDatabaseImportResponse
from backend.schemas.workflows import AdvancedWorkflowDefinitionRequest
from backend.services.advanced_workflow_runner import AdvancedWorkflowRunner

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/legacy-database", response_model=LegacyDatabaseImportResponse)
def import_legacy_database(
    db_path: DbPath,
    settings_json_path: SettingsJsonPath,
    queue: Queue,
    file: Annotated[UploadFile, File()],
) -> LegacyDatabaseImportResponse:
    import_id = str(uuid4())
    legacy_path = legacy_import_upload_path(import_id, file.filename)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with legacy_path.open("wb") as target:
            shutil.copyfileobj(file.file, target)
    finally:
        file.file.close()
    legacy_repository = LegacyImportRepository(db_path)
    try:
        legacy_repository.create(
            LegacyImport(
                id=import_id,
                source_path=str(legacy_path),
                status="pending",
            )
        )
    finally:
        legacy_repository.close()
    runner = AdvancedWorkflowRunner(db_path, settings_json_path=settings_json_path)
    try:
        run = runner.create_run(
            legacy_import_definition(import_id=import_id),
            source="legacy_import",
        )
    finally:
        runner.close()
    legacy_repository = LegacyImportRepository(db_path)
    try:
        legacy_repository.update_workflow_run_id(import_id, run.id)
    finally:
        legacy_repository.close()
    import_job_id = first_workflow_job_id(run)
    if import_job_id is not None:
        queue.wake()
    return LegacyDatabaseImportResponse(
        imported_artists=0,
        skipped_rows=0,
        total_rows=0,
        workflow_run_id=run.id,
        import_job_id=import_job_id,
        hydration_job_id=None,
        message="Legacy database import workflow started.",
    )


def first_workflow_job_id(run: object) -> str | None:
    if run is None:
        return None
    node_runs = getattr(run, "node_runs", [])
    for node_run in node_runs:
        job_ids = getattr(node_run, "job_ids", [])
        if job_ids:
            return str(job_ids[0])
    return None


def legacy_import_definition(*, import_id: str) -> AdvancedWorkflowDefinitionRequest:
    return AdvancedWorkflowDefinitionRequest.model_validate(
        {
            "name": "Legacy database import",
            "metadata": {"system_workflow": "legacy_import"},
            "nodes": [
                {
                    "id": "import",
                    "type": "legacy_database_import",
                    "title": "Import legacy artists",
                    "config": {"import_id": import_id},
                },
                {
                    "id": "hydrate",
                    "type": "legacy_import_hydration",
                    "title": "Legacy import hydration",
                    "config": {"import_id": import_id},
                },
            ],
        }
    )


def legacy_import_upload_path(import_id: str, filename: str | None) -> Path:
    suffix = ".db"
    if filename:
        lowered = filename.lower()
        for candidate in (".db", ".sqlite", ".sqlite3"):
            if lowered.endswith(candidate):
                suffix = candidate
                break
    return resources_dir() / "imports" / import_id / f"pixiv{suffix}"
