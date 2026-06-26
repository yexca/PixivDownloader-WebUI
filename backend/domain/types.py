from typing import Literal

ArtworkFileStatus = Literal[
    "remote_only", "pending", "downloading", "downloaded", "skipped", "failed"
]
DownloadInputMode = Literal["artist", "artwork"]
JobEventLevel = Literal["debug", "info", "warning", "error"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
JobType = Literal[
    "download_artist",
    "download_from_artwork",
    "rescan_artist",
    "sync_artist",
    "retry_failed",
    "retry_failed_artist",
]
ScheduledTaskAction = Literal["sync_artist", "download_artist", "retry_failed_artist"]
ScheduledTaskStatus = Literal["active", "paused", "blocked"]
