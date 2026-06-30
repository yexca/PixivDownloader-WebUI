from __future__ import annotations

from dataclasses import dataclass

from backend.domain.entities import Artist
from backend.repositories._time import utc_now
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.avatar_cache_service import AvatarCacheService
from backend.services.pixiv_client import PixivClient, PixivClientProtocol
from backend.services.unavailable_artist_policy import confirm_unavailable_artist


@dataclass(frozen=True)
class LibrarySyncSummary:
    artist: Artist
    artwork_count: int
    file_count: int
    full_sync: bool = False


class LibrarySyncService:
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

    def sync_artist(
        self,
        artist_id: str,
        *,
        source: str | None = "library_shortcut",
        full_sync: bool = False,
    ) -> LibrarySyncSummary:
        existing_artist = self.artist_repository.get_by_id(artist_id)
        now = utc_now()
        artist = self.pixiv_client.get_artist_by_user_id(artist_id)
        confirm_unavailable_artist(
            existing_artist=existing_artist,
            fetched_artist=artist,
            source=source,
        )
        artworks = (
            []
            if artist.account_status == "unavailable"
            else list(
                self.pixiv_client.get_artworks_by_user_id(
                    artist.id,
                    stop_at_artwork_id=None
                    if full_sync
                    else self.artwork_repository.max_artwork_id_by_artist(artist.id),
                )
            )
        )
        remote_latest_artwork_id = latest_artwork_id(artworks)
        record_name_change(
            self.name_history_repository,
            existing_artist=existing_artist,
            fetched_artist=artist,
        )
        synced_artist = Artist(
            id=artist.id,
            name=next_artist_text(
                artist.name,
                existing_artist.name if existing_artist else None,
                account_status=artist.account_status,
            ),
            profile_url=artist.profile_url,
            account=next_optional_artist_text(
                artist.account,
                existing_artist.account if existing_artist else None,
                account_status=artist.account_status,
            ),
            avatar_url=next_optional_artist_text(
                artist.avatar_url,
                existing_artist.avatar_url if existing_artist else None,
                account_status=artist.account_status,
            ),
            comment=next_optional_artist_text(
                artist.comment,
                existing_artist.comment if existing_artist else None,
                account_status=artist.account_status,
            ),
            last_download_id=existing_artist.last_download_id
            if existing_artist is not None
            else None,
            last_checked_at=now,
            account_status=artist.account_status,
            account_status_checked_at=now,
            account_status_reason=artist.account_status_reason,
            remote_latest_artwork_id=remote_latest_artwork_id
            or (existing_artist.remote_latest_artwork_id if existing_artist else None),
            remote_latest_checked_at=now,
        )
        self.artist_repository.upsert(synced_artist)
        self.avatar_cache_service.cache_artist_avatar(synced_artist)
        file_count = 0
        for artwork in artworks:
            self.artwork_repository.upsert(artwork)
            for file in artwork.files:
                self.file_repository.upsert_remote(file)
                file_count += 1
        return LibrarySyncSummary(
            artist=synced_artist,
            artwork_count=len(artworks),
            file_count=file_count,
            full_sync=full_sync,
        )

    def close(self) -> None:
        self.artist_repository.close()
        self.name_history_repository.close()
        self.artwork_repository.close()
        self.file_repository.close()


def latest_artwork_id(artworks: list) -> str | None:
    ids: list[int] = []
    for artwork in artworks:
        try:
            ids.append(int(artwork.id))
        except ValueError:
            continue
    if not ids:
        return None
    return str(max(ids))


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
