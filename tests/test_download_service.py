from backend.domain.entities import Artist, Artwork, ArtworkFile
from backend.repositories.legacy_artist_repository import LegacyArtistRepository
from backend.services.download_service import DownloadService
from backend.services.file_downloader import FileDownloadResult


class FakePixivClient:
    def __init__(self):
        self.user_requests = []
        self.artwork_requests = []
        self.artist_artworks_requests = []

    def get_artist_by_user_id(self, user_id: str) -> Artist:
        self.user_requests.append(user_id)
        return Artist(id=user_id, name="Artist")

    def get_artist_by_artwork_id(self, artwork_id: str) -> Artist:
        self.artwork_requests.append(artwork_id)
        return Artist(id="999", name="Artwork Artist")

    def get_artworks_by_user_id(self, user_id: str) -> list[Artwork]:
        self.artist_artworks_requests.append(user_id)
        return [
            Artwork(
                id="100",
                artist_id=user_id,
                files=(
                    ArtworkFile(
                        artwork_id="100",
                        page_index=0,
                        original_url="https://i.pximg.net/img-original/img/100_p0.jpg",
                        file_name="100_p0.jpg",
                    ),
                ),
            ),
            Artwork(
                id="101",
                artist_id=user_id,
                files=(
                    ArtworkFile(
                        artwork_id="101",
                        page_index=0,
                        original_url="https://i.pximg.net/img-original/img/101_p0.jpg",
                        file_name="101_p0.jpg",
                    ),
                ),
            ),
        ]


class FakeFileDownloader:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.calls = []

    def download(self, artist_name: str, artist_id: str, url: str) -> FileDownloadResult:
        self.calls.append((artist_name, artist_id, url))
        file_name = url.split("/")[-1]
        return FileDownloadResult(
            url=url,
            file_name=file_name,
            local_path=self.tmp_path / file_name,
            size_bytes=12,
        )


def test_download_user_id_path_downloads_and_updates_legacy_artist(tmp_path):
    repository = LegacyArtistRepository(db_path=tmp_path / "pixiv.db")
    pixiv_client = FakePixivClient()
    file_downloader = FakeFileDownloader(tmp_path)
    progress_messages = []
    service = DownloadService(
        pixiv_client=pixiv_client,
        file_downloader=file_downloader,
        artist_repository=repository,
        sleeper=lambda: None,
    )

    summary = service.download(user_id="123", progress_callback=progress_messages.append)

    assert summary.downloaded_files == 2
    assert summary.last_download_id == "101"
    assert pixiv_client.user_requests == ["123"]
    assert pixiv_client.artist_artworks_requests == ["123"]
    assert len(file_downloader.calls) == 2
    assert repository.get_by_id("123").last_download_id == "101"
    assert progress_messages[0] == "Getting user info..."


def test_download_artwork_id_path_resolves_artist_then_downloads_artist(tmp_path):
    repository = LegacyArtistRepository(db_path=tmp_path / "pixiv.db")
    pixiv_client = FakePixivClient()
    file_downloader = FakeFileDownloader(tmp_path)
    service = DownloadService(
        pixiv_client=pixiv_client,
        file_downloader=file_downloader,
        artist_repository=repository,
        sleeper=lambda: None,
    )

    summary = service.download(artwork_id="555")

    assert summary.artist.id == "999"
    assert summary.downloaded_files == 2
    assert pixiv_client.artwork_requests == ["555"]
    assert pixiv_client.artist_artworks_requests == ["999"]
    assert {call[1] for call in file_downloader.calls} == {"999"}


def test_incremental_skip_uses_legacy_last_download_id(tmp_path):
    repository = LegacyArtistRepository(db_path=tmp_path / "pixiv.db")
    repository.upsert(Artist(id="123", name="Existing", last_download_id="100"))
    pixiv_client = FakePixivClient()
    file_downloader = FakeFileDownloader(tmp_path)
    service = DownloadService(
        pixiv_client=pixiv_client,
        file_downloader=file_downloader,
        artist_repository=repository,
        sleeper=lambda: None,
    )

    summary = service.download(user_id="123")

    assert summary.skipped_files == 1
    assert summary.downloaded_files == 1
    assert len(file_downloader.calls) == 1
    assert file_downloader.calls[0][2].endswith("101_p0.jpg")
    assert repository.get_by_id("123").last_download_id == "101"
