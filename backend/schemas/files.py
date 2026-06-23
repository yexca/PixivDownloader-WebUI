from __future__ import annotations

from pydantic import BaseModel

from backend.domain.entities import ArtworkFile


class ArtworkFileResponse(BaseModel):
    id: int | None
    artwork_id: str
    page_index: int
    original_url: str
    local_path: str | None
    file_name: str
    size_bytes: int | None
    status: str
    downloaded_at: str | None
    error_message: str | None


class ArtworkFileListResponse(BaseModel):
    items: list[ArtworkFileResponse]
    total: int


def artwork_file_response(file: ArtworkFile) -> ArtworkFileResponse:
    return ArtworkFileResponse(
        id=file.id,
        artwork_id=file.artwork_id,
        page_index=file.page_index,
        original_url=file.original_url,
        local_path=str(file.local_path) if file.local_path is not None else None,
        file_name=file.file_name,
        size_bytes=file.size_bytes,
        status=file.status,
        downloaded_at=file.downloaded_at,
        error_message=file.error_message,
    )
