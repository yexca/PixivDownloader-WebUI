from __future__ import annotations

from dataclasses import dataclass

from backend.domain.entities import Artist
from backend.repositories._time import utc_now
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.pixiv_client import PixivClient, PixivClientProtocol


@dataclass(frozen=True)
class LibrarySyncSummary:
    artist: Artist
    artwork_count: int
    file_count: int


class LibrarySyncService:
    def __init__(
        self,
        *,
        pixiv_client: PixivClientProtocol | None = None,
        artist_repository: ArtistRepository | None = None,
        artwork_repository: ArtworkRepository | None = None,
        file_repository: ArtworkFileRepository | None = None,
    ) -> None:
        self.pixiv_client = pixiv_client or PixivClient()
        self.artist_repository = artist_repository or ArtistRepository()
        self.artwork_repository = artwork_repository or ArtworkRepository()
        self.file_repository = file_repository or ArtworkFileRepository()

    def sync_artist(self, artist_id: str) -> LibrarySyncSummary:
        existing_artist = self.artist_repository.get_by_id(artist_id)
        artist = self.pixiv_client.get_artist_by_user_id(artist_id)
        artworks = list(self.pixiv_client.get_artworks_by_user_id(artist.id))
        synced_artist = Artist(
            id=artist.id,
            name=artist.name,
            profile_url=artist.profile_url,
            account=artist.account,
            avatar_url=artist.avatar_url,
            comment=artist.comment,
            last_download_id=existing_artist.last_download_id
            if existing_artist is not None
            else None,
            last_checked_at=utc_now(),
        )
        self.artist_repository.upsert(synced_artist)
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
        )

    def close(self) -> None:
        self.artist_repository.close()
        self.artwork_repository.close()
        self.file_repository.close()
