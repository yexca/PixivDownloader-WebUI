from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    download_path: str
    refresh_token_configured: bool
    refresh_token_preview: str
    request_base_delay_seconds: float
    request_random_delay_seconds: float
    max_concurrent_downloads: int
    overwrite_existing_files: bool
    skip_existing_files: bool


class SettingsUpdateRequest(BaseModel):
    download_path: str = Field(min_length=1)
    refresh_token: str | None = None
    request_base_delay_seconds: float = Field(ge=0)
    request_random_delay_seconds: float = Field(ge=0)
    max_concurrent_downloads: int = Field(ge=1)
    overwrite_existing_files: bool
    skip_existing_files: bool
