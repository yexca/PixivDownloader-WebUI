from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.services.file_downloader import FileDownloadResult
from backend.workers.download_worker import DownloadWorker


class FakePixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(id=user_id, name="Artist")

    def get_artist_by_artwork_id(self, _artwork_id: str) -> Artist:
        return Artist(id="123", name="Artist")

    def get_artworks_by_user_id(self, user_id: str) -> list[Artwork]:
        return [
            Artwork(
                id="200",
                artist_id=user_id,
                title="Title",
                files=(
                    ArtworkFile(
                        artwork_id="200",
                        page_index=0,
                        original_url="https://i.pximg.net/img-original/img/200_p0.jpg",
                        file_name="200_p0.jpg",
                    ),
                ),
            )
        ]


class FakeFileDownloader:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def download(self, _artist_name: str, _artist_id: str, url: str) -> FileDownloadResult:
        file_path = self.tmp_path / url.split("/")[-1]
        file_path.write_bytes(b"image")
        return FileDownloadResult(
            url=url,
            file_name=file_path.name,
            local_path=file_path,
            size_bytes=file_path.stat().st_size,
        )


class FailingFileDownloader:
    def download(self, _artist_name: str, _artist_id: str, _url: str) -> FileDownloadResult:
        raise OSError("disk write failed")


def test_worker_updates_job_and_file_statuses(tmp_path):
    db_path = tmp_path / "pixiv.db"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="queued",
                input_user_id="123",
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakePixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "completed"
    assert job.total_files == 1
    assert job.completed_files == 1
    file_repository = ArtworkFileRepository(db_path)
    try:
        files = file_repository.list_by_artwork("200")
        assert files[0].status == "downloaded"
        assert files[0].size_bytes == 5
    finally:
        file_repository.close()


def test_worker_observes_pre_cancelled_job(tmp_path):
    db_path = tmp_path / "pixiv.db"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="queued",
                input_user_id="123",
                cancel_requested=True,
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakePixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "cancelled"
    assert job.cancel_requested is True


def test_worker_persists_failed_file_and_job_event(tmp_path):
    db_path = tmp_path / "pixiv.db"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="queued",
                input_user_id="123",
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakePixivClient,
        file_downloader_factory=FailingFileDownloader,
    )

    job = worker.run_job("job-1")

    assert job.status == "completed"
    assert job.failed_files == 1
    file_repository = ArtworkFileRepository(db_path)
    job_repository = JobRepository(db_path)
    try:
        files = file_repository.list_by_artwork("200")
        events = job_repository.list_events("job-1")
        assert files[0].status == "failed"
        assert files[0].error_message == "disk write failed"
        assert any(event.message == "Job completed" for event in events)
    finally:
        file_repository.close()
        job_repository.close()
