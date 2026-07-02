from __future__ import annotations

from pydantic import BaseModel


class LegacyDatabaseImportResponse(BaseModel):
    imported_artists: int
    skipped_rows: int
    total_rows: int
    workflow_run_id: str | None = None
    import_job_id: str | None = None
    hydration_job_id: str | None = None
    message: str
