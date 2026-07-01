from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from backend.domain.entities import WorkflowTriggerConfig, WorkflowTriggerTarget


class DownloadCreateRequest(BaseModel):
    user_id: str | None = None
    artwork_id: str | None = None
    mode: Literal["artist", "artwork"] = "artist"
    force_rescan: bool = False
    retry_failed: bool = False
    full_download: bool = False
    pending_only: bool = False
    max_artworks: int | None = None
    min_artwork_id: str | None = None
    max_artwork_id: str | None = None
    naming_rule: str | None = None
    only_new_artworks: bool = False
    stop_if_artwork_count_above: int | None = None
    naming_tag_variants: list[dict[str, str]] | None = None
    tag_variants: list[dict[str, str]] | None = None

    @model_validator(mode="after")
    def validate_input(self) -> DownloadCreateRequest:
        if bool(self.user_id) == bool(self.artwork_id):
            raise ValueError("exactly one of user_id or artwork_id must be provided")
        if self.full_download and self.retry_failed:
            raise ValueError("full_download and retry_failed cannot both be enabled")
        if self.pending_only and (self.full_download or self.retry_failed):
            raise ValueError("pending_only cannot be combined with full_download or retry_failed")
        if self.max_artworks is not None and self.max_artworks < 1:
            raise ValueError("max_artworks must be at least 1")
        if self.stop_if_artwork_count_above is not None and self.stop_if_artwork_count_above < 1:
            raise ValueError("stop_if_artwork_count_above must be at least 1")
        for field_name in ("min_artwork_id", "max_artwork_id"):
            value = getattr(self, field_name)
            if value is not None and value.strip() and not value.strip().isdigit():
                raise ValueError(f"{field_name} must contain digits only")
        return self


class DownloadCreateResponse(BaseModel):
    job_id: str
    status: str


def download_request_options(request: DownloadCreateRequest) -> dict[str, object]:
    return {
        "full_download": request.full_download,
        "pending_only": request.pending_only,
        "max_artworks": request.max_artworks,
        "min_artwork_id": request.min_artwork_id.strip() if request.min_artwork_id else None,
        "max_artwork_id": request.max_artwork_id.strip() if request.max_artwork_id else None,
        "naming_rule": request.naming_rule.strip() if request.naming_rule else None,
        "only_new_artworks": request.only_new_artworks,
        "stop_if_artwork_count_above": request.stop_if_artwork_count_above,
        "naming_tag_variants": request.naming_tag_variants or [],
        "tag_variants": request.tag_variants or [],
    }


def download_request_workflow_config(request: DownloadCreateRequest) -> WorkflowTriggerConfig:
    target = WorkflowTriggerTarget(
        type="single_artwork" if request.artwork_id else "single_artist",
        artist_id=request.user_id,
        artwork_id=request.artwork_id,
    )
    return WorkflowTriggerConfig(
        target=target,
        actions=("download_artist",),
        download_options=download_request_options(request),
        max_artists_per_run=1,
    )
