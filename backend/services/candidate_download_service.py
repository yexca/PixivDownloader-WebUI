from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import ExistingFileBehavior
from backend.domain.entities import Artist, ArtworkFile
from backend.repositories._time import utc_now
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.workflow_candidate_repository import WorkflowCandidateRepository
from backend.services.download_service import artwork_id_from_url, render_naming_rule
from backend.services.file_downloader import FileDownloader


@dataclass(frozen=True)
class CandidateDownloadSummary:
    total_files: int
    downloaded_files: int
    skipped_files: int
    failed_files: int
    artist_ids: list[str]


class CandidateDownloadService:
    def __init__(
        self,
        *,
        candidate_repository: WorkflowCandidateRepository,
        artist_repository: ArtistRepository,
        file_repository: ArtworkFileRepository,
        file_downloader: FileDownloader,
    ) -> None:
        self.candidate_repository = candidate_repository
        self.artist_repository = artist_repository
        self.file_repository = file_repository
        self.file_downloader = file_downloader

    def download(
        self,
        *,
        candidate_set_id: str,
        artist_id: str | None = None,
        naming_rule: str | None = None,
    ) -> CandidateDownloadSummary:
        source = self._candidate_source(candidate_set_id)
        artworks = self.candidate_repository.list_artworks(
            candidate_set_id,
            artist_id=artist_id,
        )
        downloaded_files = 0
        skipped_files = 0
        failed_files = 0
        total_files = 0
        latest_download_id_by_artist: dict[str, int] = {}
        touched_artist_ids: list[str] = []
        for artwork in artworks:
            artist = self.artist_repository.get_by_id(artwork.artist_id)
            if artist is None:
                continue
            if artist.id not in touched_artist_ids:
                touched_artist_ids.append(artist.id)
            files = self.candidate_repository.list_files_for_artwork(
                artwork.id,
                candidate_source=source,
            )
            total_files += len(files)
            for file in files:
                try:
                    self.file_repository.update_status(
                        file.id or 0,
                        status="downloading",
                        error_message=None,
                    )
                    relative_path = render_naming_rule(
                        naming_rule,
                        artist=artist,
                        artwork=artwork,
                        file=file,
                    )
                    result = self.file_downloader.download(
                        artist.name,
                        artist.id,
                        file.original_url,
                        relative_path=relative_path,
                    )
                except Exception as exc:
                    failed_files += 1
                    self._mark_failed(file, str(exc))
                    continue
                if result.skipped:
                    skipped_files += 1
                    self._mark_downloaded(file, result.local_path, result.size_bytes, skipped=True)
                else:
                    downloaded_files += 1
                    self._mark_downloaded(file, result.local_path, result.size_bytes)
                current_id = artwork_id_from_url(file.original_url)
                previous_id = latest_download_id_by_artist.get(
                    artist.id,
                    int(artist.last_download_id or 0),
                )
                if current_id > previous_id:
                    latest_download_id_by_artist[artist.id] = current_id

        self._update_artist_cursors(latest_download_id_by_artist)
        return CandidateDownloadSummary(
            total_files=total_files,
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
            artist_ids=touched_artist_ids,
        )

    def _candidate_source(self, candidate_set_id: str) -> str:
        candidate_set = self.candidate_repository.get_candidate_set(candidate_set_id)
        if candidate_set is None:
            raise ValueError(f"candidate set not found: {candidate_set_id}")
        config_source = candidate_set.config.get("collect_mode")
        return str(config_source or candidate_set.source)

    def _mark_downloaded(
        self,
        file: ArtworkFile,
        local_path: object,
        size_bytes: int,
        *,
        skipped: bool = False,
    ) -> None:
        if file.id is None:
            return
        self.file_repository.update_status(
            file.id,
            status="skipped" if skipped else "downloaded",
            local_path=local_path,
            size_bytes=size_bytes,
            downloaded_at=None if skipped else utc_now(),
            error_message=None,
        )

    def _mark_failed(self, file: ArtworkFile, message: str) -> None:
        if file.id is None:
            return
        self.file_repository.update_status(file.id, status="failed", error_message=message)

    def _update_artist_cursors(self, latest_download_id_by_artist: dict[str, int]) -> None:
        for artist_id, latest_download_id in latest_download_id_by_artist.items():
            artist = self.artist_repository.get_by_id(artist_id)
            if artist is None:
                continue
            self.artist_repository.upsert(
                Artist(
                    **{
                        **artist.__dict__,
                        "last_download_id": str(latest_download_id),
                    }
                )
            )


def existing_file_behavior_from_conflict_mode(value: object) -> ExistingFileBehavior:
    if value == "overwrite":
        return "overwrite"
    if value == "rename":
        return "save_duplicate"
    return "skip"
