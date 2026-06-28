from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.domain.types import (
    ArtistAccountStatus,
    ArtworkFileStatus,
    JobEventLevel,
    JobStatus,
    JobType,
    ScheduledTaskAction,
    ScheduledTaskArtistSelection,
    ScheduledTaskFilterType,
    ScheduledTaskStatus,
    ScheduledTaskTargetType,
)


@dataclass(frozen=True)
class Artist:
    id: str
    name: str
    profile_url: str = ""
    account: str | None = None
    avatar_url: str | None = None
    comment: str | None = None
    last_download_id: str | None = None
    last_checked_at: str | None = None
    account_status: ArtistAccountStatus = "unknown"
    account_status_checked_at: str | None = None
    account_status_reason: str | None = None
    remote_latest_artwork_id: str | None = None
    remote_latest_checked_at: str | None = None


@dataclass(frozen=True)
class LocalTag:
    id: int
    name: str


@dataclass(frozen=True)
class ArtistNameHistory:
    artist_id: str
    name: str
    source: str = "pixiv"
    id: int | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None


@dataclass(frozen=True)
class ArtworkFile:
    artwork_id: str
    page_index: int
    original_url: str
    file_name: str
    status: ArtworkFileStatus = "pending"
    local_path: Path | None = None
    id: int | None = None
    size_bytes: int | None = None
    downloaded_at: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class Artwork:
    id: str
    artist_id: str
    title: str = ""
    type: str | None = None
    caption: str | None = None
    page_count: int = 0
    width: int | None = None
    height: int | None = None
    sanity_level: int | None = None
    restrict_value: int | None = None
    tags: tuple[str, ...] = ()
    pixiv_created_at: str | None = None
    files: tuple[ArtworkFile, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DownloadProgress:
    message: str
    total_files: int = 0
    completed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0


@dataclass(frozen=True)
class Job:
    id: str
    type: JobType
    status: JobStatus
    input_user_id: str | None = None
    input_artwork_id: str | None = None
    options: dict[str, object] = field(default_factory=dict)
    workflow_run_id: str | None = None
    workflow_item_id: int | None = None
    workflow_source: str | None = None
    artist_id: str | None = None
    total_files: int = 0
    completed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    cancel_requested: bool = False
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    level: JobEventLevel
    message: str
    payload: dict[str, object] | None = None
    id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class ScheduledTask:
    id: int | None
    name: str
    action: ScheduledTaskAction
    status: ScheduledTaskStatus
    target_artist_id: str
    interval_days: int
    run_after_startup: bool = True
    last_run_at: str | None = None
    last_success_at: str | None = None
    next_run_at: str | None = None
    last_job_id: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    config: ScheduledTaskConfig | None = None
    last_run_summary: dict[str, object] | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ScheduledTaskTarget:
    type: ScheduledTaskTargetType
    artist_id: str | None = None
    artwork_id: str | None = None
    tag: str | None = None
    tags: tuple[str, ...] = ()
    days: int | None = None


@dataclass(frozen=True)
class ScheduledTaskFilter:
    type: ScheduledTaskFilterType
    days: int | None = None


@dataclass(frozen=True)
class ScheduledTaskConfig:
    target: ScheduledTaskTarget
    filters: tuple[ScheduledTaskFilter, ...] = ()
    actions: tuple[ScheduledTaskAction, ...] = ("download_artist",)
    download_options: dict[str, object] = field(default_factory=dict)
    max_artists_per_run: int = 25
    artist_selection: ScheduledTaskArtistSelection = "oldest_checked_first"
    skip_unavailable_artists: bool = True
