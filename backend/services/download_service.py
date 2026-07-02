from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.errors import DownloadSkippedError, JobCancelledError
from backend.domain.entities import Artist, Artwork, ArtworkFile, DownloadProgress
from backend.domain.types import ArtworkFileStatus
from backend.repositories._time import utc_now
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.avatar_cache_service import AvatarCacheService
from backend.services.file_downloader import FileDownloader
from backend.services.library_sync_service import LibrarySyncService
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
    full_download: bool = False
    pending_only: bool = False
    source: str | None = None
    max_artworks: int | None = None
    min_artwork_id: str | None = None
    max_artwork_id: str | None = None
    naming_rule: str | None = None
    only_new_artworks: bool = False
    stop_if_artwork_count_above: int | None = None
    naming_tag_variants: tuple[dict[str, str], ...] = ()
    tag_variants: tuple[dict[str, str], ...] = ()


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
        avatar_cache_service: AvatarCacheService | None = None,
        sleeper: Callable[[], None] | None = None,
    ) -> None:
        resolved_sleeper = sleeper or RandomSleep()
        self.pixiv_client = pixiv_client or PixivClient(sleeper=resolved_sleeper)
        self.file_downloader = file_downloader or FileDownloader()
        self.artist_repository = artist_repository or ArtistRepository()
        self.name_history_repository = name_history_repository or ArtistNameHistoryRepository()
        db_path = repository_db_path(self.artist_repository)
        self.artwork_repository = artwork_repository or ArtworkRepository(db_path)
        self.file_repository = file_repository or ArtworkFileRepository(db_path)
        self.avatar_cache_service = avatar_cache_service or AvatarCacheService()
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
        self._report(progress_callback, "Syncing Pixiv metadata...")
        artist = self._sync_metadata(
            user_id=user_id,
            artwork_id=artwork_id,
            options=resolved_options,
        )
        self._check_cancelled(cancel_callback)

        self._report(progress_callback, "Selecting files to download...")
        artworks = self._known_artworks(artist.id)
        artworks = filter_artworks(artworks, resolved_options)
        if (
            resolved_options.stop_if_artwork_count_above is not None
            and len(artworks) > resolved_options.stop_if_artwork_count_above
        ):
            raise DownloadSkippedError(
                "workflow rule stopped download: artwork count "
                f"{len(artworks)} is above {resolved_options.stop_if_artwork_count_above}"
            )
        last_downloaded_artwork_id = optional_artwork_id(artist.last_download_id)
        if resolved_options.only_new_artworks and last_downloaded_artwork_id is not None:
            artworks = [
                artwork
                for artwork in artworks
                if optional_artwork_id(artwork.id) is not None
                and optional_artwork_id(artwork.id) > last_downloaded_artwork_id
            ]
        self._check_cancelled(cancel_callback)

        files = self._select_known_files(
            artworks=artworks,
            retry_failed=resolved_options.retry_failed,
            pending_only=resolved_options.pending_only,
        )
        artwork_by_id = {artwork.id: artwork for artwork in artworks}

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
                artwork = artwork_by_id.get(file.artwork_id)
                variant = matching_tag_variant(artwork, resolved_options)
                behavior = variant.get("behavior", "download")
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
                if behavior == "skip":
                    skipped_files += 1
                    self._mark_file(file, status="skipped", error_message=None)
                    current_download_id = artwork_id_from_url(file.original_url)
                    if last_download_id < current_download_id:
                        last_download_id = current_download_id
                    active_file = None
                    continue
                if behavior == "retry_failed" and file.status != "failed":
                    skipped_files += 1
                    self._mark_file(file, status="skipped", error_message=None)
                    current_download_id = artwork_id_from_url(file.original_url)
                    if last_download_id < current_download_id:
                        last_download_id = current_download_id
                    active_file = None
                    continue
                current_download_id = artwork_id_from_url(file.original_url)
                if (
                    not resolved_options.retry_failed
                    and not resolved_options.force_rescan
                    and not resolved_options.full_download
                    and not resolved_options.pending_only
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
                    relative_path = render_naming_rule(
                        resolved_options.naming_rule,
                        artist=artist,
                        artwork=artwork,
                        file=file,
                        variants=resolved_options.naming_tag_variants,
                        tag_variants=resolved_options.tag_variants,
                    )
                    if relative_path is None:
                        result = self.file_downloader.download(
                            artist.name,
                            artist.id,
                            file.original_url,
                        )
                    else:
                        result = self.file_downloader.download(
                            artist.name,
                            artist.id,
                            file.original_url,
                            relative_path=relative_path,
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
        latest_artist = self.artist_repository.get_by_id(artist.id) or artist
        updated_artist = Artist(
            **{
                **latest_artist.__dict__,
                "last_download_id": str(last_download_id),
            }
        )
        self.artist_repository.upsert(updated_artist)
        self.avatar_cache_service.cache_artist_avatar(updated_artist)
        self._report(progress_callback, "Inserted database")

        return DownloadSummary(
            artist=artist,
            total_files=total_files,
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            failed_files=failed_files,
            last_download_id=str(last_download_id),
        )

    def _sync_metadata(
        self,
        *,
        user_id: str | None,
        artwork_id: str | None,
        options: DownloadOptions,
    ) -> Artist:
        resolved_artist_id = user_id
        if resolved_artist_id is None:
            if artwork_id is None:
                raise ValueError("artwork_id is required")
            resolved_artist_id = self.pixiv_client.get_artist_by_artwork_id(artwork_id).id
        sync_service = LibrarySyncService(
            pixiv_client=self.pixiv_client,
            artist_repository=self.artist_repository,
            name_history_repository=self.name_history_repository,
            artwork_repository=self.artwork_repository,
            file_repository=self.file_repository,
            avatar_cache_service=self.avatar_cache_service,
        )
        summary = sync_service.sync_artist(
            resolved_artist_id,
            source=options.source,
            full_sync=options.full_download or options.force_rescan,
        )
        return summary.artist

    def _known_artworks(self, artist_id: str) -> list[Artwork]:
        return self.artwork_repository.list_all_by_artist(artist_id)

    def _select_known_files(
        self,
        *,
        artworks: list[Artwork],
        retry_failed: bool,
        pending_only: bool,
    ) -> list[ArtworkFile]:
        selected_files: list[ArtworkFile] = []
        for artwork in artworks:
            for file in self.file_repository.list_by_artwork(artwork.id):
                existing = file
                if retry_failed and (existing is None or existing.status != "failed"):
                    continue
                if pending_only and (
                    existing is None or existing.status not in {"pending", "remote_only"}
                ):
                    continue
                selected_files.append(file)
        return selected_files

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
        if file.id is None:
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

    def _report(self, progress_callback: ProgressCallback | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def close(self) -> None:
        self.artist_repository.close()
        self.name_history_repository.close()
        self.artwork_repository.close()
        self.file_repository.close()


def artwork_id_from_url(url: str) -> int:
    file_name = url.split("/")[-1]
    artwork_part = file_name.split("_")[0].split("-")[0]
    return int(artwork_part)


def repository_db_path(repository: Any) -> Path | None:
    conn = getattr(repository, "conn", None)
    if conn is None:
        return None
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except Exception:
        return None
    for row in rows:
        keys = row.keys() if hasattr(row, "keys") else ()
        name = row["name"] if "name" in keys else row[1]
        file_path = row["file"] if "file" in keys else row[2]
        if name == "main" and file_path:
            return Path(str(file_path))
    return None


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


def filter_artworks(artworks: list[Artwork], options: DownloadOptions) -> list[Artwork]:
    selected = artworks
    min_id = optional_artwork_id(options.min_artwork_id)
    max_id = optional_artwork_id(options.max_artwork_id)
    if min_id is not None or max_id is not None:
        selected = [
            artwork
            for artwork in selected
            if artwork_id_in_range(artwork.id, min_id=min_id, max_id=max_id)
        ]
    if options.max_artworks is not None:
        selected = selected[: options.max_artworks]
    return selected


def optional_artwork_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def artwork_id_in_range(artwork_id: str, *, min_id: int | None, max_id: int | None) -> bool:
    try:
        value = int(artwork_id)
    except ValueError:
        return False
    if min_id is not None and value < min_id:
        return False
    return not (max_id is not None and value > max_id)


def render_naming_rule(
    rule: str | None,
    *,
    artist: Artist,
    artwork: Artwork | None,
    file: ArtworkFile,
    variants: tuple[dict[str, str], ...] = (),
    tag_variants: tuple[dict[str, str], ...] = (),
) -> str | None:
    variant = matching_tag_variant(artwork, DownloadOptions(tag_variants=tag_variants))
    if variant.get("naming_rule"):
        rule = variant["naming_rule"]
    elif artwork is not None:
        for variant in variants:
            tag = (variant.get("tag") or "").casefold()
            variant_rule = variant.get("naming_rule") or ""
            if tag and variant_rule and any(item.casefold() == tag for item in artwork.tags):
                rule = variant_rule
                break
    if not rule:
        return None
    original_filename = file.original_url.split("/")[-1]
    ext = original_filename.rsplit(".", 1)[-1] if "." in original_filename else ""
    tokens = {
        "artist": artist.name,
        "artist_id": artist.id,
        "artwork_id": file.artwork_id,
        "title": artwork.title if artwork is not None else "",
        "page": str(file.page_index),
        "original_filename": original_filename,
        "ext": ext,
        "type": artwork.type if artwork is not None and artwork.type else "",
        "download_date": utc_now()[:10],
        "ai": "AI" if artwork is not None and is_ai_artwork(artwork) else "",
    }
    result = rule
    for key, value in tokens.items():
        if value == "":
            result = remove_empty_token_prefix(result, key)
        result = result.replace(f"{{{key}}}", value)
    result = result.strip().strip("/\\")
    if not result:
        return None
    if "{ext}" not in rule and "." not in result.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] and ext:
        result = f"{result}.{ext}"
    return result


def matching_tag_variant(artwork: Artwork | None, options: DownloadOptions) -> dict[str, str]:
    if artwork is None:
        return {}
    for variant in options.tag_variants:
        tag = (variant.get("tag") or "").casefold()
        if tag and any(item.casefold() == tag for item in artwork.tags):
            return variant
    return {}


def remove_empty_token_prefix(rule: str, token: str) -> str:
    return re.sub(rf"[-_\s]*\{{{re.escape(token)}\}}", "", rule)


def is_ai_artwork(artwork: Artwork) -> bool:
    ai_tags = {
        "ai",
        "ai-generated",
        "ai生成",
        "ai生成作品",
        "aiイラスト",
        "ai生成イラスト",
        "ai 画作",
        "ai 생성",
    }
    return any(tag.strip().casefold() in ai_tags for tag in artwork.tags)
