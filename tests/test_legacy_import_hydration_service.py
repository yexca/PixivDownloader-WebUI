import pytest

from backend.core.errors import PixivApiError
from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile
from backend.repositories.artist_name_history_repository import ArtistNameHistoryRepository
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.services.legacy_import_hydration_service import (
    LegacyImportHydrationArtistTarget,
    LegacyImportHydrationRetryableError,
    LegacyImportHydrationService,
)


class FakePixivClient:
    def __init__(self):
        self.artists = {
            "123": Artist(id="123", name="Fetched Artist"),
            "456": Artist(
                id="456",
                name="456",
                account_status="unavailable",
                account_status_reason="page not found",
            ),
            "789": Artist(id="789", name="No Cursor"),
        }
        self.artworks = {
            "123": [
                Artwork(
                    id="100",
                    artist_id="123",
                    title="Old",
                    files=(
                        ArtworkFile(
                            artwork_id="100",
                            page_index=0,
                            original_url="https://i.pximg.net/img-original/img/100_p0.jpg",
                            file_name="100_p0.jpg",
                        ),
                        ArtworkFile(
                            artwork_id="100",
                            page_index=1,
                            original_url="https://i.pximg.net/img-original/img/100_p1.jpg",
                            file_name="100_p1.jpg",
                        ),
                    ),
                ),
                Artwork(
                    id="105",
                    artist_id="123",
                    title="New",
                    files=(
                        ArtworkFile(
                            artwork_id="105",
                            page_index=0,
                            original_url="https://i.pximg.net/img-original/img/105_p0.jpg",
                            file_name="105_p0.jpg",
                        ),
                    ),
                ),
            ],
            "789": [
                Artwork(
                    id="200",
                    artist_id="789",
                    files=(
                        ArtworkFile(
                            artwork_id="200",
                            page_index=0,
                            original_url="https://i.pximg.net/img-original/img/200_p0.jpg",
                            file_name="200_p0.jpg",
                        ),
                    ),
                )
            ],
        }

    def get_artist_by_user_id(self, user_id: str) -> Artist:
        artist = self.artists.get(user_id)
        if artist is None:
            raise PixivApiError(f"failed to fetch Pixiv user {user_id}")
        return artist

    def get_artist_by_artwork_id(self, _artwork_id: str) -> Artist:
        raise NotImplementedError

    def get_artworks_by_user_id(
        self,
        user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        return self.artworks.get(user_id, [])


def test_legacy_hydration_marks_cursor_artworks_downloaded_and_newer_remote(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, artist_repository, artwork_repository, file_repository = make_service(db_path)
    artist_repository.upsert(Artist(id="123", name="Legacy", last_download_id="100"))

    summary = service.hydrate(
        [LegacyImportHydrationArtistTarget("123", legacy_latest_download_id="100")]
    )

    assert summary.completed_artists == 1
    assert summary.artwork_count == 2
    assert artwork_repository.count_by_artist("123") == 2
    assert [file.status for file in file_repository.list_by_artwork("100")] == [
        "downloaded",
        "downloaded",
    ]
    assert file_repository.list_by_artwork("105")[0].status == "remote_only"


def test_legacy_hydration_does_not_invent_missing_artwork_ids(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, _artist_repository, artwork_repository, _file_repository = make_service(db_path)

    service.hydrate([LegacyImportHydrationArtistTarget("123", legacy_latest_download_id="104")])

    assert artwork_repository.get_by_id("101") is None
    assert artwork_repository.get_by_id("102") is None
    assert artwork_repository.get_by_id("103") is None
    assert artwork_repository.get_by_id("104") is None


def test_legacy_hydration_unavailable_artist_completed_unavailable(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, artist_repository, _artwork_repository, _file_repository = make_service(db_path)
    artist_repository.upsert(Artist(id="456", name="Legacy Closed", last_download_id="300"))

    summary = service.hydrate(
        [LegacyImportHydrationArtistTarget("456", legacy_latest_download_id="300")]
    )

    artist = artist_repository.get_by_id("456")
    assert summary.completed_unavailable_artists == 1
    assert artist.account_status == "unavailable"
    assert artist.account_status_reason == "page not found"


def test_legacy_hydration_idempotent_and_preserves_existing_downloaded(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, artist_repository, _artwork_repository, file_repository = make_service(db_path)
    artist_repository.upsert(Artist(id="123", name="Legacy", last_download_id="110"))

    service.hydrate([LegacyImportHydrationArtistTarget("123", legacy_latest_download_id="100")])
    service.hydrate([LegacyImportHydrationArtistTarget("123", legacy_latest_download_id="100")])

    assert [file.status for file in file_repository.list_by_artwork("100")] == [
        "downloaded",
        "downloaded",
    ]
    assert file_repository.list_by_artwork("105")[0].status == "remote_only"
    assert artist_repository.get_by_id("123").last_download_id == "110"


def test_legacy_hydration_missing_cursor_hydrates_remote_metadata_only(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, _artist_repository, artwork_repository, file_repository = make_service(db_path)

    summary = service.hydrate([LegacyImportHydrationArtistTarget("789")])

    assert summary.skipped_no_legacy_cursor_artists == 1
    assert artwork_repository.get_by_id("200") is not None
    assert file_repository.list_by_artwork("200")[0].status == "remote_only"


def test_legacy_hydration_retryable_failure_preserves_successes(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    service, _artist_repository, artwork_repository, file_repository = make_service(db_path)

    with pytest.raises(LegacyImportHydrationRetryableError) as exc_info:
        service.hydrate(
            [
                LegacyImportHydrationArtistTarget("123", legacy_latest_download_id="100"),
                LegacyImportHydrationArtistTarget("missing", legacy_latest_download_id="500"),
            ]
        )

    assert exc_info.value.summary.completed_artists == 1
    assert exc_info.value.summary.failed_retryable_artists == 1
    assert artwork_repository.count_by_artist("123") == 2
    assert file_repository.list_by_artwork("100")[0].status == "downloaded"


def make_service(db_path):
    migrate_database(db_path, settings_json_path=db_path.with_suffix(".json"))
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)
    service = LegacyImportHydrationService(
        pixiv_client=FakePixivClient(),
        artist_repository=artist_repository,
        name_history_repository=ArtistNameHistoryRepository(db_path),
        artwork_repository=artwork_repository,
        file_repository=file_repository,
    )
    return service, artist_repository, artwork_repository, file_repository
