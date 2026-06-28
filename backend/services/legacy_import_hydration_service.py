from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from backend.domain.entities import Artist, Artwork
from backend.repositories._time import utc_now
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.avatar_cache_service import AvatarCacheService
from backend.services.download_service import optional_artwork_id
from backend.services.library_sync_service import (
    latest_artwork_id,
    next_artist_text,
    next_optional_artist_text,
    record_name_change,
)
from backend.services.pixiv_client import PixivClient, PixivClientProtocol

LegacyHydrationProgressCallback = Callable[["LegacyImportHydrationArtistResult"], None]


@dataclass(frozen=True)
class LegacyImportHydrationArtistTarget:
    artist_id: str
    legacy_latest_download_id: str | None = None


@dataclass(frozen=True)
class LegacyImportHydrationArtistResult:
    artist_id: str
    status: str
    artwork_count: int = 0
    file_count: int = 0
    downloaded_file_count: int = 0
    remote_file_count: int = 0
    reason: str | None = None


@dataclass(frozen=True)
class LegacyImportHydrationSummary:
    total_artists: int
    completed_artists: int = 0
    completed_unavailable_artists: int = 0
    skipped_no_legacy_cursor_artists: int = 0
    failed_retryable_artists: int = 0
    artwork_count: int = 0
    file_count: int = 0
    downloaded_file_count: int = 0
    remote_file_count: int = 0
    results: tuple[LegacyImportHydrationArtistResult, ...] = field(default_factory=tuple)


class LegacyImportHydrationService:
    def __init__(
        self,
        *,
        pixiv_client: PixivClientProtocol | None = None,
        artist_repository: ArtistRepository | None = None,
        name_history_repository: ArtistNameHistoryRepository | None = None,
        artwork_repository: ArtworkRepository | None = None,
        file_repository: ArtworkFileRepository | None = None,
        avatar_cache_service: AvatarCacheService | None = None,
    ) -> None:
        self.pixiv_client = pixiv_client or PixivClient()
        self.artist_repository = artist_repository or ArtistRepository()
        self.name_history_repository = name_history_repository or ArtistNameHistoryRepository()
        self.artwork_repository = artwork_repository or ArtworkRepository()
        self.file_repository = file_repository or ArtworkFileRepository()
        self.avatar_cache_service = avatar_cache_service or AvatarCacheService()

    def hydrate(
        self,
        targets: list[LegacyImportHydrationArtistTarget],
        *,
        progress_callback: LegacyHydrationProgressCallback | None = None,
    ) -> LegacyImportHydrationSummary:
        results: list[LegacyImportHydrationArtistResult] = []
        retryable_errors: list[Exception] = []
        for target in targets:
            try:
                result = self._hydrate_artist(target)
            except Exception as exc:
                result = LegacyImportHydrationArtistResult(
                    artist_id=target.artist_id,
                    status="failed_retryable",
                    reason=str(exc),
                )
                retryable_errors.append(exc)
            results.append(result)
            if progress_callback is not None:
                progress_callback(result)

        summary = summarize_results(results, total_artists=len(targets))
        if retryable_errors:
            raise LegacyImportHydrationRetryableError(summary)
        return summary

    def _hydrate_artist(
        self,
        target: LegacyImportHydrationArtistTarget,
    ) -> LegacyImportHydrationArtistResult:
        existing_artist = self.artist_repository.get_by_id(target.artist_id)
        now = utc_now()
        fetched_artist = self.pixiv_client.get_artist_by_user_id(target.artist_id)
        record_name_change(
            self.name_history_repository,
            existing_artist=existing_artist,
            fetched_artist=fetched_artist,
        )
        if fetched_artist.account_status == "unavailable":
            unavailable_artist = merge_legacy_hydrated_artist(
                existing_artist=existing_artist,
                fetched_artist=fetched_artist,
                legacy_latest_download_id=target.legacy_latest_download_id,
                now=now,
                artworks=[],
            )
            self.artist_repository.upsert(unavailable_artist)
            return LegacyImportHydrationArtistResult(
                artist_id=target.artist_id,
                status="completed_unavailable",
                reason=fetched_artist.account_status_reason,
            )

        artworks = list(self.pixiv_client.get_artworks_by_user_id(fetched_artist.id))
        synced_artist = merge_legacy_hydrated_artist(
            existing_artist=existing_artist,
            fetched_artist=fetched_artist,
            legacy_latest_download_id=target.legacy_latest_download_id,
            now=now,
            artworks=artworks,
        )
        self.artist_repository.upsert(synced_artist)
        self.avatar_cache_service.cache_artist_avatar(synced_artist)

        legacy_latest_id = optional_artwork_id(target.legacy_latest_download_id)
        artwork_count = 0
        file_count = 0
        downloaded_file_count = 0
        remote_file_count = 0
        for artwork in artworks:
            self.artwork_repository.upsert(artwork)
            artwork_count += 1
            artwork_id = optional_artwork_id(artwork.id)
            legacy_downloaded = (
                legacy_latest_id is not None
                and artwork_id is not None
                and artwork_id <= legacy_latest_id
            )
            for file in artwork.files:
                if legacy_downloaded:
                    self.file_repository.upsert_legacy_downloaded(file)
                    downloaded_file_count += 1
                else:
                    self.file_repository.upsert_remote(file)
                    remote_file_count += 1
                file_count += 1

        return LegacyImportHydrationArtistResult(
            artist_id=target.artist_id,
            status="completed" if legacy_latest_id is not None else "skipped_no_legacy_cursor",
            artwork_count=artwork_count,
            file_count=file_count,
            downloaded_file_count=downloaded_file_count,
            remote_file_count=remote_file_count,
        )

    def close(self) -> None:
        self.artist_repository.close()
        self.name_history_repository.close()
        self.artwork_repository.close()
        self.file_repository.close()


class LegacyImportHydrationRetryableError(Exception):
    def __init__(self, summary: LegacyImportHydrationSummary) -> None:
        self.summary = summary
        super().__init__(
            "legacy import hydration had "
            f"{summary.failed_retryable_artists} retryable artist failure(s)"
        )


def merge_legacy_hydrated_artist(
    *,
    existing_artist: Artist | None,
    fetched_artist: Artist,
    legacy_latest_download_id: str | None,
    now: str,
    artworks: list[Artwork],
) -> Artist:
    existing_last_download_id = existing_artist.last_download_id if existing_artist else None
    return Artist(
        id=fetched_artist.id,
        name=next_artist_text(
            fetched_artist.name,
            existing_artist.name if existing_artist else None,
            account_status=fetched_artist.account_status,
        ),
        profile_url=fetched_artist.profile_url
        or (existing_artist.profile_url if existing_artist else ""),
        account=next_optional_artist_text(
            fetched_artist.account,
            existing_artist.account if existing_artist else None,
            account_status=fetched_artist.account_status,
        ),
        avatar_url=next_optional_artist_text(
            fetched_artist.avatar_url,
            existing_artist.avatar_url if existing_artist else None,
            account_status=fetched_artist.account_status,
        ),
        comment=next_optional_artist_text(
            fetched_artist.comment,
            existing_artist.comment if existing_artist else None,
            account_status=fetched_artist.account_status,
        ),
        last_download_id=greater_artwork_id(existing_last_download_id, legacy_latest_download_id),
        last_checked_at=now,
        account_status=fetched_artist.account_status,
        account_status_checked_at=now,
        account_status_reason=fetched_artist.account_status_reason,
        remote_latest_artwork_id=latest_artwork_id(artworks)
        or (existing_artist.remote_latest_artwork_id if existing_artist else None),
        remote_latest_checked_at=now,
    )


def greater_artwork_id(first: str | None, second: str | None) -> str | None:
    first_id = optional_artwork_id(first)
    second_id = optional_artwork_id(second)
    if first_id is None:
        return second
    if second_id is None:
        return first
    return first if first_id >= second_id else second


def summarize_results(
    results: list[LegacyImportHydrationArtistResult],
    *,
    total_artists: int,
) -> LegacyImportHydrationSummary:
    return LegacyImportHydrationSummary(
        total_artists=total_artists,
        completed_artists=sum(1 for result in results if result.status == "completed"),
        completed_unavailable_artists=sum(
            1 for result in results if result.status == "completed_unavailable"
        ),
        skipped_no_legacy_cursor_artists=sum(
            1 for result in results if result.status == "skipped_no_legacy_cursor"
        ),
        failed_retryable_artists=sum(
            1 for result in results if result.status == "failed_retryable"
        ),
        artwork_count=sum(result.artwork_count for result in results),
        file_count=sum(result.file_count for result in results),
        downloaded_file_count=sum(result.downloaded_file_count for result in results),
        remote_file_count=sum(result.remote_file_count for result in results),
        results=tuple(results),
    )


def legacy_hydration_targets_from_options(
    options: dict[str, object],
) -> list[LegacyImportHydrationArtistTarget]:
    legacy_latest_by_artist = options.get("legacy_latest_download_id_by_artist")
    if not isinstance(legacy_latest_by_artist, dict):
        legacy_latest_by_artist = {}
    artist_ids = options.get("artist_ids")
    if not isinstance(artist_ids, list):
        return []
    targets: list[LegacyImportHydrationArtistTarget] = []
    for artist_id in artist_ids:
        if not isinstance(artist_id, str) or not artist_id.strip():
            continue
        legacy_latest_download_id = legacy_latest_by_artist.get(artist_id)
        targets.append(
            LegacyImportHydrationArtistTarget(
                artist_id=artist_id.strip(),
                legacy_latest_download_id=str(legacy_latest_download_id).strip()
                if legacy_latest_download_id
                else None,
            )
        )
    return targets
