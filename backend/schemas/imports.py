from __future__ import annotations

from pydantic import BaseModel


class LegacyDatabaseImportResponse(BaseModel):
    imported_artists: int
    skipped_rows: int
    total_rows: int
    message: str
