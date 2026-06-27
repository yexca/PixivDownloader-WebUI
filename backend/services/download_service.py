from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.core.errors import JobCancelledError
from backend.domain.entities import Artist, Artwork, ArtworkFile, DownloadProgress
from backend.domain.types import ArtworkFileStatus
from backend.repositories._time import utc_now
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.file_downloader import FileDownloader
from backend.services.pixiv_client import PixivClient, PixivClientProtocol
from backend.services.random_sleep import RandomSleep

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str | DownloadProgress], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class DownloadSummary:
    artist: Artist
    total_files: int
    downloaded_files: int
    skipped_files: int
    failed_files: int
    last_download_id: str


@dataclass(frozen=True)
class DownloadOptions:
    force_rescan: bool = False
    retry_failed: bool = False
    skip_existing_files: bool = True


class DownloadService:
    def __init__(
        self,
        *,
        pixiv_client: PixivClientProtocol | None = None,
        file_downloader: FileDownloader | None = None,
        artist_repository: ArtistRepository | None = None,
        name_history_repository: ArtistNameHistoryRepository | None = None,
        artwork_repository: ArtworkRepository | None = None,
        file_repository: ArtworkFileRepository | None = None,
        sleeper: Callable[[], None] | None = None,
    ) -> None:
        resolved_sleeper = sleeper or RandomSleep()
        self.pixiv_client = pixiv_client or PixivClient(sleeper=resolved_sleeper)
        self.file_downloader = file_downloader or FileDownloader()
        self.artist_repository = artist_repository or ArtistRepository()
        self.name_history_repository = name_history_repository or ArtistNameHistoryRepository()
        self.artwork_repository = artwork_repository
        self.file_repository = file_repository
        self.sleeper = resolved_sleeper

    def download(
        self,
        *,
        user_id: str | None = None,
        artwork_id: str | None = None,
        options: DownloadOptions | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_callback: CancelCallback | None = None,
    ) -> DownloadSummary:
        if bool(user_id) == bool(artwork_id):
            raise ValueError("exactly one of user_id or artwork_id is required")

        resolved_options = options or DownloadOptions()
        self._report(progress_callback, "Getting user info...")
        artist = self._resolve_artist(user_id=user_id, artwork_id=artwork_id)
        self._check_cancelled(cancel_callback)

        self._report(progress_callback, "Got user info. Getting artworks info...")
        remote_checked_at = utc_now()
        artworks = (
            []
            if artist.account_status == "unavailable"
            else list(self.pixiv_client.get_artworks_by_user_id(artist.id))
        )
        self._check_cancelled(cancel_callback)

        self._report(progress_callback, "Got artworks info. Getting download links...")
        files = self._persist_discovered_artworks(
            artist=artist,
            artworks=artworks,
            retry_failed=resolved_options.retry_failed,
        )

        downloaded_files = 0
        skipped_files = 0
        failed_files = 0
        total_files = len(files)
        last_download_id = int(artist.last_download_id or 0)
        active_file: ArtworkFile | None = None

        try:
            for file in files:
                active_file = file
                self._check_cancelled(cancel_callback)
                self._report(
                    progress_callback,
                    DownloadProgress(
                        message=f"Downloading {file.file_name}",
                        total_files=total_files,
                        completed_files=downloaded_files,
                        skipped_files=skipped_files,
                        failed_files=failed_files,
                    ),
                )
                current_download_id = artwork_id_from_url(file.original_url)
                if (
                    not resolved_options.retry_failed
                    and not resolved_options.force_rescan
                    and artist.last_download_id
                    and current_download_id <= int(artist.last_download_id)
                ):
                    logger.info("Already downloaded artwork: %s", current_download_id)
                    skipped_files += 1
                    self._mark_file(
                        file,
                        status="skipped",
                        error_message=None,
                    )
                    active_file = None
                    continue

                if self.sleeper is not None:
                    self.sleeper()
                self._mark_file(file, status="downloading", error_message=None)
                self._check_cancelled(cancel_callback)
                try:
                    result = self.file_downloader.download(
                        artist.name,
                        artist.id,
                        file.original_url,
                    )
                except Exception as exc:
                    failed_files += 1
                    self._mark_file(file, status="failed", error_message=str(exc))
                    logger.warning("failed to download %s", file.original_url, exc_info=True)
                else:
                    if result.skipped:
                        skipped_files += 1
                        status: ArtworkFileStatus = "skipped"
                    else:
                        downloaded_files += 1
                        status = "downloaded"
                    self._mark_file(
                        file,
                        status=status,
                        local_path=result.local_path,
                        size_bytes=result.size_bytes,
                        downloaded_at=utc_now() if not result.skipped else None,
                        error_message=None,
                    )
                    if last_download_id < current_download_id:
                        last_download_id = current_download_id
                active_file = None
        except JobCancelledError:
            if active_file is not None:
                failed_files += 1
                self._mark_file(
                    active_file,
                    status="failed",
                    error_message="Download cancelled before this file completed.",
                )
            self._report(
                progress_callback,
                DownloadProgress(
                    message="Download cancelled",
                    total_files=total_files,
                    completed_files=downloaded_files,
                    skipped_files=skipped_files,
                    failed_files=failed_files,
                ),
            )
            raise

        self._report(progress_callback, "Download completed, Inserting database...")
        self.artist_repository.upsert(
            Artist(
                id=artist.id,
                name=artist.name,
                profile_url=artist.profile_url,
                account=artist.account,
                avatar_url=artist.avatar_url,
                comment=artist.comment,
                last_download_id=str(last_download_id),
                last_checked_at=artist.last_checked_at,
                account_status=artist.account_status,
                account_status_checked_at=artist.account_status_checked_at,
                account_status_reason=artist.account_status_reason,
                remote_latest_artwork_id=latest_artwork_id(artworks)
                or artist.remote_latest_artwork_id,
                remote_latest_checked_at=remote_checked_at,
            )
        )
        self._report(progress_callback, "Inserted database")

        return DownloadSummary(
            artist=artist,
            total_files=total_files,
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
            last_download_id=str(last_download_id),
        )

    def _persist_discovered_artworks(
        self,
        *,
        artist: Artist,
        artworks: list[Artwork],
        retry_failed: bool,
    ) -> list[ArtworkFile]:
        self.artist_repository.upsert(artist)
        if self.artwork_repository is None or self.file_repository is None:
            return [file for artwork in artworks for file in artwork.files]

        selected_files: list[ArtworkFile] = []
        for artwork in artworks:
            self.artwork_repository.upsert(artwork)
            for file in artwork.files:
                existing = self._existing_file(file)
                if retry_failed and (existing is None or existing.status != "failed"):
                    continue
                file_id = self.file_repository.upsert(
                    ArtworkFile(
                        id=file.id,
                        artwork_id=file.artwork_id,
                        page_index=file.page_index,
                        original_url=file.original_url,
                        file_name=file.file_name,
                        status="pending",
                        local_path=file.local_path,
                        size_bytes=file.size_bytes,
                    )
                )
                selected_files.append(
                    ArtworkFile(
                        id=file_id,
                        artwork_id=file.artwork_id,
                        page_index=file.page_index,
                        original_url=file.original_url,
                        file_name=file.file_name,
                    )
                )
        return selected_files

    def _existing_file(self, file: ArtworkFile) -> ArtworkFile | None:
        if self.file_repository is None:
            return None
        return next(
            (
                existing
                for existing in self.file_repository.list_by_artwork(file.artwork_id)
                if existing.page_index == file.page_index
            ),
            None,
        )

    def _mark_file(
        self,
        file: ArtworkFile,
        *,
        status: ArtworkFileStatus,
        local_path: Path | str | None = None,
        size_bytes: int | None = None,
        downloaded_at: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if self.file_repository is None or file.id is None:
            return
        self.file_repository.update_status(
            file.id,
            status=status,
            local_path=local_path,
            size_bytes=size_bytes,
            downloaded_at=downloaded_at,
            error_message=error_message,
        )

    def _check_cancelled(self, cancel_callback: CancelCallback | None) -> None:
        if cancel_callback is not None and cancel_callback():
            from backend.core.errors import JobCancelledError

            raise JobCancelledError("job cancellation requested")

    def _resolve_artist(self, *, user_id: str | None, artwork_id: str | None) -> Artist:
        if user_id:
            existing_artist = self.artist_repository.get_by_id(user_id)
            fetched_artist = self.pixiv_client.get_artist_by_user_id(user_id)
            now = utc_now()
            record_name_change(
                self.name_history_repository,
                existing_artist=existing_artist,
                fetched_artist=fetched_artist,
            )
            if existing_artist is None:
                return Artist(
                    **{
                        **fetched_artist.__dict__,
                        "last_checked_at": now,
                        "account_status_checked_at": now,
                        "remote_latest_checked_at": now,
                    }
                )
            return merge_fetched_artist(existing_artist, fetched_artist, now=now)

        if artwork_id is None:
            raise ValueError("artwork_id is required")
        artwork_artist = self.pixiv_client.get_artist_by_artwork_id(artwork_id)
        existing_artist = self.artist_repository.get_by_id(artwork_artist.id)
        if existing_artist is not None:
            return existing_artist
        return artwork_artist

    def _report(self, progress_callback: ProgressCallback | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def close(self) -> None:
        self.artist_repository.close()
        self.name_history_repository.close()
        if self.artwork_repository is not None:
            self.artwork_repository.close()
        if self.file_repository is not None:
            self.file_repository.close()


def artwork_id_from_url(url: str) -> int:
    file_name = url.split("/")[-1]
    artwork_part = file_name.split("_")[0].split("-")[0]
    return int(artwork_part)


def latest_artwork_id(artworks: list[Artwork]) -> str | None:
    ids: list[int] = []
    for artwork in artworks:
        try:
            ids.append(int(artwork.id))
        except ValueError:
            continue
    if not ids:
        return None
    return str(max(ids))


def merge_fetched_artist(existing: Artist, fetched: Artist, *, now: str) -> Artist:
    return Artist(
        id=fetched.id,
        name=next_artist_text(
            fetched.name,
            existing.name,
            account_status=fetched.account_status,
        ),
        profile_url=fetched.profile_url or existing.profile_url,
        account=next_optional_artist_text(
            fetched.account,
            existing.account,
            account_status=fetched.account_status,
        ),
        avatar_url=next_optional_artist_text(
            fetched.avatar_url,
            existing.avatar_url,
            account_status=fetched.account_status,
        ),
        comment=next_optional_artist_text(
            fetched.comment,
            existing.comment,
            account_status=fetched.account_status,
        ),
        last_download_id=existing.last_download_id,
        last_checked_at=now,
        account_status=fetched.account_status,
        account_status_checked_at=now,
        account_status_reason=fetched.account_status_reason,
        remote_latest_artwork_id=existing.remote_latest_artwork_id,
        remote_latest_checked_at=existing.remote_latest_checked_at,
    )


def record_name_change(
    repository: ArtistNameHistoryRepository,
    *,
    existing_artist: Artist | None,
    fetched_artist: Artist,
) -> None:
    if existing_artist is not None:
        repository.record_name(existing_artist.id, existing_artist.name)
    if fetched_artist.account_status == "available":
        repository.record_name(fetched_artist.id, fetched_artist.name)


def next_artist_text(value: str, fallback: str | None, *, account_status: str) -> str:
    text = value.strip()
    if account_status == "available" and text:
        return text
    return fallback or value


def next_optional_artist_text(
    value: str | None,
    fallback: str | None,
    *,
    account_status: str,
) -> str | None:
    if account_status == "available" and value:
        return value
    return fallback
