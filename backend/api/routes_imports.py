from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from backend.api.dependencies import DbPath
from backend.schemas.imports import LegacyDatabaseImportResponse
from backend.services.legacy_import_service import LegacyDatabaseImportService

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/legacy-database", response_model=LegacyDatabaseImportResponse)
def import_legacy_database(
    db_path: DbPath,
    file: Annotated[UploadFile, File()],
) -> LegacyDatabaseImportResponse:
    try:
        summary = LegacyDatabaseImportService(db_path).import_file(file.file)
    finally:
        file.file.close()
    return LegacyDatabaseImportResponse(
        imported_artists=summary.imported_artists,
        skipped_rows=summary.skipped_rows,
        total_rows=summary.total_rows,
        message=f"Imported {summary.imported_artists} artists from legacy database.",
    )
