from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from backend.domain.entities import Artist, DownloadProgress
from backend.repositories.legacy_artist_repository import LegacyArtistRepository
from backend.services.file_downloader import FileDownloader
from backend.services.pixiv_client import PixivClient, PixivClientProtocol
from backend.services.random_sleep import RandomSleep

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str | DownloadProgress], None]


@dataclass(frozen=True)
class DownloadSummary:
    artist: Artist
    total_files: int
    downloaded_files: int
    skipped_files: int
    failed_files: int
    last_download_id: str


class DownloadService:
    def __init__(
        self,
        *,
        pixiv_client: PixivClientProtocol | None = None,
        file_downloader: FileDownloader | None = None,
        artist_repository: LegacyArtistRepository | None = None,
        sleeper: Callable[[], None] | None = None,
    ) -> None:
        resolved_sleeper = sleeper or RandomSleep()
        self.pixiv_client = pixiv_client or PixivClient(sleeper=resolved_sleeper)
        self.file_downloader = file_downloader or FileDownloader()
        self.artist_repository = artist_repository or LegacyArtistRepository()
        self.sleeper = resolved_sleeper

    def download(
        self,
        *,
        user_id: str | None = None,
        artwork_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> DownloadSummary:
        if bool(user_id) == bool(artwork_id):
            raise ValueError("exactly one of user_id or artwork_id is required")

        self._report(progress_callback, "Getting user info...")
        artist = self._resolve_artist(user_id=user_id, artwork_id=artwork_id)

        self._report(progress_callback, "Got user info. Getting artworks info...")
        artworks = list(self.pixiv_client.get_artworks_by_user_id(artist.id))

        self._report(progress_callback, "Got artworks info. Getting download links...")
        files = [file for artwork in artworks for file in artwork.files]

        downloaded_files = 0
        skipped_files = 0
        failed_files = 0
        total_files = len(files)
        last_download_id = int(artist.last_download_id or 0)

        for index, file in enumerate(files, start=1):
            self._report(progress_callback, f"Downloading NO. {index}, Total: {total_files}")
            current_download_id = artwork_id_from_url(file.original_url)
            if artist.last_download_id and current_download_id <= int(artist.last_download_id):
                logger.info("Already downloaded artwork: %s", current_download_id)
                skipped_files += 1
                continue

            if self.sleeper is not None:
                self.sleeper()

            result = self.file_downloader.download(artist.name, artist.id, file.original_url)
            if result.skipped:
                skipped_files += 1
            else:
                downloaded_files += 1
            if last_download_id < current_download_id:
                last_download_id = current_download_id

        self._report(progress_callback, "Download completed, Inserting database...")
        self.artist_repository.upsert(artist, str(last_download_id))
        self._report(progress_callback, "Inserted database")

        return DownloadSummary(
            artist=artist,
            total_files=total_files,
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
            last_download_id=str(last_download_id),
        )

    def _resolve_artist(self, *, user_id: str | None, artwork_id: str | None) -> Artist:
        if user_id:
            existing_artist = self.artist_repository.get_by_id(user_id)
            if existing_artist is not None:
                return existing_artist
            return self.pixiv_client.get_artist_by_user_id(user_id)

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


def artwork_id_from_url(url: str) -> int:
    file_name = url.split("/")[-1]
    artwork_part = file_name.split("_")[0].split("-")[0]
    return int(artwork_part)
