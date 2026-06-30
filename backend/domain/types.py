from typing import Literal

ArtworkFileStatus = Literal[
    "remote_only", "pending", "downloading", "downloaded", "skipped", "failed"
]
DownloadInputMode = Literal["artist", "artwork"]
JobEventLevel = Literal["debug", "info", "warning", "error"]
JobStatus = Literal["inactive", "queued", "running", "completed", "failed", "cancelled"]
JobType = Literal[
    "download_artist",
    "download_from_artwork",
    "rescan_artist",
    "sync_artist",
    "retry_failed",
    "retry_failed_artist",
    "hydrate_legacy_import",
    "resolve_workflow_targets",
    "resolve_artist_targets",
    "download_candidate_artist",
    "download_candidate_set",
]
ScheduledTaskAction = Literal["sync_artist", "download_artist", "retry_failed_artist"]
ScheduledTaskStatus = Literal["active", "inactive", "paused", "blocked", "archived"]
ScheduledTaskTargetType = Literal[
    "artists",
    "artworks",
    "single_artist",
    "single_artwork",
    "all_artists",
    "artists_with_tag",
    "artists_not_checked",
]
ScheduledTaskArtistSource = Literal["artist_ids", "artwork_ids"]
ScheduledTaskFilterType = Literal["last_checked_before_days", "has_failed_files"]
ScheduledTaskArtistSelection = Literal["oldest_checked_first", "newest_checked_first", "random"]
ArtistAccountStatus = Literal["unknown", "available", "unavailable"]
FailureReason = Literal["auth", "disk", "network", "cancelled", "target", "rule", "unknown"]
