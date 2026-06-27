from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    download_path: str
    download_path_editable: bool
    runtime_mode: str
    refresh_token_configured: bool
    refresh_token_preview: str
    request_base_delay_seconds: float
    request_random_delay_seconds: float
    max_concurrent_downloads: int
    min_free_space_gb: float
    overwrite_existing_files: bool
    skip_existing_files: bool
    library_stale_check_days: int


class SettingsUpdateRequest(BaseModel):
    download_path: str | None = Field(default=None, min_length=1)
    refresh_token: str | None = None
    request_base_delay_seconds: float | None = Field(default=None, ge=0)
    request_random_delay_seconds: float | None = Field(default=None, ge=0)
    max_concurrent_downloads: int | None = Field(default=None, ge=1)
    min_free_space_gb: float | None = Field(default=None, ge=0)
    overwrite_existing_files: bool | None = None
    skip_existing_files: bool | None = None
    library_stale_check_days: int | None = Field(default=None, ge=1)


class AuthValidationResponse(BaseModel):
    ok: bool
    message: str


class PixivAuthStartResponse(BaseModel):
    flow_id: str
    login_url: str
    expires_at: str


class PixivBrowserAuthStartResponse(PixivAuthStartResponse):
    novnc_url: str


class PixivBrowserAuthStatusResponse(BaseModel):
    flow_id: str
    status: str
    expires_at: str
    error: str | None = None


class PixivBrowserAuthServiceStatusResponse(BaseModel):
    configured: bool
    running: bool
    novnc_url: str
    start_command: str
    stop_command: str
    message: str


class PixivBrowserAuthCallbackRequest(BaseModel):
    flow_id: str = Field(min_length=1)
    callback_url: str | None = None
    error: str | None = None


class PixivAuthCompleteRequest(BaseModel):
    flow_id: str = Field(min_length=1)
    code_or_callback_url: str = Field(min_length=1)


class PixivAuthCompleteResponse(SettingsResponse):
    message: str


class PixivAuthRefreshResponse(SettingsResponse):
    message: str
