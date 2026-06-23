from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.domain.types import ArtworkFileStatus


@dataclass(frozen=True)
class Artist:
    id: str
    name: str
    profile_url: str = ""
    last_download_id: str | None = None


@dataclass(frozen=True)
class ArtworkFile:
    artwork_id: str
    page_index: int
    original_url: str
    file_name: str
    status: ArtworkFileStatus = "pending"
    local_path: Path | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class Artwork:
    id: str
    artist_id: str
    title: str = ""
    files: tuple[ArtworkFile, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DownloadProgress:
    message: str
    total_files: int = 0
    completed_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
