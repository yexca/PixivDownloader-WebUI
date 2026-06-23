from typing import Literal

ArtworkFileStatus = Literal["pending", "downloading", "downloaded", "skipped", "failed"]
DownloadInputMode = Literal["artist", "artwork"]
JobEventLevel = Literal["debug", "info", "warning", "error"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
JobType = Literal["download_artist", "download_from_artwork", "rescan_artist", "retry_failed"]
