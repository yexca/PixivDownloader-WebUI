from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.core.config import ExistingFileBehavior
from backend.core.errors import JobCancelledError
from backend.domain.entities import DownloadProgress
from backend.repositories._time import utc_now
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.file_repository import ArtworkFileDownloadClaim, ArtworkFileRepository
from backend.repositories.workflow_candidate_repository import WorkflowCandidateRepository
from backend.services.download_service import (
    DownloadOptions,
    matching_tag_variant,
    render_naming_rule,
)
from backend.services.file_downloader import FileDownloader
from backend.services.pixiv_rate_policy import raise_if_cancelled


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
        candidate_source: str | None = None,
        options: DownloadOptions | None = None,
        cancel_callback: Callable[[], bool] | None = None,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> CandidateDownloadSummary:
        source = candidate_source or self._candidate_source(candidate_set_id)
        options = options or DownloadOptions()
        artworks = self.candidate_repository.list_artworks(
            candidate_set_id,
            artist_id=artist_id,
        )
        selected = []
        for artwork in artworks:
            raise_if_cancelled(cancel_callback)
            artist = self.artist_repository.get_by_id(artwork.artist_id)
            if artist is None:
                continue
            if options.only_new_artworks and int(artwork.id) <= int(artist.last_download_id or 0):
                continue
            files = self.candidate_repository.list_files_for_artwork(
                artwork.id,
                candidate_source=source,
            )
            selected.append((artist, artwork, files))
        downloaded_files = 0
        skipped_files = 0
        failed_files = 0
        total_files = sum(len(files) for _, _, files in selected)
        touched_artist_ids: list[str] = []
        for artist, artwork, files in selected:
            raise_if_cancelled(cancel_callback)
            if artist.id not in touched_artist_ids:
                touched_artist_ids.append(artist.id)
            for file in files:
                with self.file_repository.claim_download(
                    file.id or 0, cancel_callback=cancel_callback
                ) as claim:
                    file = claim.file
                    if (
                        (source == "failed_files" and file.status != "failed")
                        or (
                            source == "pending_files"
                            and file.status not in {"pending", "remote_only"}
                        )
                        or (
                            source == "new_since_last_download"
                            and file.status in {"downloaded", "skipped"}
                        )
                    ):
                        skipped_files += 1
                        self._progress(
                            progress_callback,
                            total_files,
                            downloaded_files,
                            skipped_files,
                            failed_files,
                        )
                        continue
                    raise_if_cancelled(cancel_callback)
                    behavior = matching_tag_variant(artwork, options).get("behavior", "download")
                    if behavior == "skip" or (
                        behavior == "retry_failed" and file.status != "failed"
                    ):
                        skipped_files += 1
                        if behavior == "skip":
                            self.file_repository.update_claim(claim, status="skipped")
                        self._progress(
                            progress_callback,
                            total_files,
                            downloaded_files,
                            skipped_files,
                            failed_files,
                        )
                        continue
                    try:
                        relative_path = render_naming_rule(
                            naming_rule,
                            artist=artist,
                            artwork=artwork,
                            file=file,
                            variants=options.naming_tag_variants,
                            tag_variants=options.tag_variants,
                        )
                        extra = (
                            {
                                "cancel_callback": cancel_callback,
                                "retry_incomplete": file.status in {"failed", "downloading"},
                            }
                            if isinstance(self.file_downloader, FileDownloader)
                            else {}
                        )
                        result = self.file_downloader.download(
                            artist.name,
                            artist.id,
                            file.original_url,
                            relative_path=relative_path,
                            **extra,
                        )
                    except JobCancelledError:
                        raise
                    except Exception as exc:
                        failed_files += 1
                        self._mark_failed(claim, str(exc))
                        self._progress(
                            progress_callback,
                            total_files,
                            downloaded_files,
                            skipped_files,
                            failed_files,
                        )
                        continue
                    if result.skipped:
                        skipped_files += 1
                        self._mark_downloaded(
                            claim, result.local_path, result.size_bytes, skipped=True
                        )
                    else:
                        downloaded_files += 1
                        self._mark_downloaded(claim, result.local_path, result.size_bytes)
                    self.artist_repository.advance_download_cursor(artist.id)
                    self._progress(
                        progress_callback,
                        total_files,
                        downloaded_files,
                        skipped_files,
                        failed_files,
                    )

        for touched_id in touched_artist_ids:
            self.artist_repository.advance_download_cursor(touched_id)
        raise_if_cancelled(cancel_callback)
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
        config_source = candidate_set.config.get("candidate_source") or candidate_set.config.get(
            "collect_mode"
        )
        return str(config_source or candidate_set.source)

    def _mark_downloaded(
        self,
        claim: ArtworkFileDownloadClaim,
        local_path: object,
        size_bytes: int,
        *,
        skipped: bool = False,
    ) -> None:
        self.file_repository.update_claim(
            claim,
            status="skipped" if skipped else "downloaded",
            local_path=local_path,
            size_bytes=size_bytes,
            downloaded_at=None if skipped else utc_now(),
            error_message=None,
        )

    def _mark_failed(self, claim: ArtworkFileDownloadClaim, message: str) -> None:
        self.file_repository.update_claim(claim, status="failed", error_message=message)

    @staticmethod
    def _progress(callback, total, downloaded, skipped, failed) -> None:
        if callback is not None:
            callback(
                DownloadProgress("Downloading candidate files", total, downloaded, skipped, failed)
            )


def existing_file_behavior_from_conflict_mode(value: object) -> ExistingFileBehavior:
    if value == "overwrite":
        return "overwrite"
    if value == "rename":
        return "save_duplicate"
    return "skip"
