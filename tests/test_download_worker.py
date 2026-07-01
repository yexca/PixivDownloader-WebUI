import json

from backend.core.paths import downloads_dir
from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository
from backend.repositories.job_repository import JobRepository
from backend.repositories.workflow_candidate_repository import (
    CollectArtworkCandidatesRequest,
    WorkflowCandidateRepository,
)
from backend.repositories.workflow_run_repository import (
    WorkflowRun,
    WorkflowRunRepository,
)
from backend.services.file_downloader import FileDownloadResult
from backend.workers.download_worker import DownloadWorker


class FakePixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(id=user_id, name="Artist")

    def get_artist_by_artwork_id(self, _artwork_id: str) -> Artist:
        return Artist(id="123", name="Artist")

    def get_artworks_by_user_id(
        self,
        user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del stop_at_artwork_id
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


class ResolvingPixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(id=user_id, name=f"Artist {user_id}")

    def get_artist_by_artwork_id(self, artwork_id: str) -> Artist:
        artists = {
            "111": Artist(id="456", name="Resolved Artist"),
            "222": Artist(id="123", name="Duplicate Artist"),
        }
        return artists[artwork_id]

    def get_artworks_by_user_id(
        self,
        _user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del stop_at_artwork_id
        return []


class FakeLegacyPixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        if user_id == "closed":
            return Artist(
                id=user_id,
                name="Closed",
                account_status="unavailable",
                account_status_reason="page not found",
            )
        return Artist(id=user_id, name="Legacy Artist")

    def get_artworks_by_user_id(
        self,
        user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del stop_at_artwork_id
        if user_id == "closed":
            return []
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
                    ArtworkFile(
                        artwork_id="200",
                        page_index=1,
                        original_url="https://i.pximg.net/img-original/img/200_p1.jpg",
                        file_name="200_p1.jpg",
                    ),
                ),
            )
        ]


class FakeUnavailablePixivClient:
    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(
            id=user_id,
            name=user_id,
            account_status="unavailable",
            account_status_reason="Your access is currently restricted.",
        )

    def get_artist_by_artwork_id(self, _artwork_id: str) -> Artist:
        raise NotImplementedError

    def get_artworks_by_user_id(
        self,
        _user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del stop_at_artwork_id
        return []


class RecordingSyncPixivClient:
    stop_markers: list[str | None] = []

    def get_artist_by_user_id(self, user_id: str) -> Artist:
        return Artist(id=user_id, name="Artist")

    def get_artist_by_artwork_id(self, _artwork_id: str) -> Artist:
        raise NotImplementedError

    def get_artworks_by_user_id(
        self,
        user_id: str,
        *,
        stop_at_artwork_id: str | None = None,
    ) -> list[Artwork]:
        del user_id
        self.stop_markers.append(stop_at_artwork_id)
        return [
            Artwork(
                id="300",
                artist_id="123",
                title="Title",
                files=(
                    ArtworkFile(
                        artwork_id="300",
                        page_index=0,
                        original_url="https://i.pximg.net/img-original/img/300_p0.jpg",
                        file_name="300_p0.jpg",
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


class CandidateFileDownloader:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.calls: list[str] = []

    def download(
        self,
        _artist_name: str,
        _artist_id: str,
        url: str,
        *,
        relative_path: str | None = None,
    ) -> FileDownloadResult:
        self.calls.append(relative_path or url)
        file_path = self.tmp_path / (relative_path or url.split("/")[-1])
        file_path.parent.mkdir(parents=True, exist_ok=True)
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
    db_path = tmp_path / "pixiv.sqlite3"
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
    db_path = tmp_path / "pixiv.sqlite3"
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
    db_path = tmp_path / "pixiv.sqlite3"
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


def test_worker_file_downloader_uses_runtime_enforced_download_path(tmp_path, monkeypatch):
    db_path = tmp_path / "pixiv.sqlite3"
    settings_path = tmp_path / "settings.json"
    settings_example_path = tmp_path / "settings.example.json"
    settings_example_path.write_text(
        json.dumps(
            {
                "download_path": "D:\\Downloads",
                "refresh_token": "token",
                "request_base_delay_seconds": 0,
                "request_random_delay_seconds": 0,
                "max_concurrent_downloads": 1,
                "existing_file_behavior": "skip",
            }
        ),
        encoding="utf-8",
    )
    settings_path.write_text("{}", encoding="utf-8")
    migrate_database(db_path, settings_json_path=settings_path)
    monkeypatch.setenv("PIXIVDOWNLOADER_RUNTIME", "docker")

    worker = DownloadWorker(db_path=db_path, settings_json_path=settings_path)
    file_downloader = worker._create_file_downloader()

    assert file_downloader.download_path == downloads_dir()


def test_legacy_hydration_progress_uses_artist_counts(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="hydrate_legacy_import",
                status="queued",
                total_files=2,
                options={
                    "artist_ids": ["123", "closed"],
                    "legacy_latest_download_id_by_artist": {"123": "200", "closed": "100"},
                },
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakeLegacyPixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "completed"
    assert job.total_files == 2
    assert job.completed_files == 2
    assert job.skipped_files == 0
    assert job.failed_files == 0


def test_worker_requires_confirmation_for_new_manual_unavailable_artist(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="download_artist",
                status="queued",
                input_user_id="missing",
                workflow_source="download_api",
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakeUnavailablePixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "failed"
    assert "Confirm the artist ID" in job.error_message
    assert job.options["error_code"] == "pixiv_target_unavailable"
    assert job.options["error_retryable"] is False
    repository = JobRepository(db_path)
    try:
        events = repository.list_events("job-1")
    finally:
        repository.close()
    assert events[-1].payload is not None
    assert events[-1].payload["error_code"] == "pixiv_target_unavailable"
    artist_repository = ArtistRepository(db_path)
    try:
        assert artist_repository.get_by_id("missing") is None
    finally:
        artist_repository.close()


def test_worker_accepts_library_shortcut_unavailable_artist(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="sync_artist",
                status="queued",
                input_user_id="missing",
                workflow_source="library_shortcut",
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakeUnavailablePixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "completed"
    artist_repository = ArtistRepository(db_path)
    try:
        artist = artist_repository.get_by_id("missing")
        assert artist is not None
        assert artist.account_status == "unavailable"
    finally:
        artist_repository.close()


def test_sync_artist_job_passes_full_sync_option(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    RecordingSyncPixivClient.stop_markers = []
    repository = JobRepository(db_path)
    try:
        repository.create(
            Job(
                id="job-1",
                type="sync_artist",
                status="queued",
                input_user_id="123",
                options={"full_sync": True},
            )
        )
    finally:
        repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=RecordingSyncPixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("job-1")

    assert job.status == "completed"
    assert RecordingSyncPixivClient.stop_markers == [None]


def test_worker_resolves_workflow_targets_without_creating_action_jobs(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    job_repository = JobRepository(db_path)
    try:
        job_repository.create(
            Job(
                id="target-resolver-1",
                type="resolve_workflow_targets",
                status="queued",
                workflow_source="advanced_workflow",
                options={
                    "artist_ids": ["123"],
                    "artwork_ids": ["111", "222"],
                    "max_targets_per_run": 25,
                },
            )
        )
    finally:
        job_repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=ResolvingPixivClient,
        file_downloader_factory=lambda: FakeFileDownloader(tmp_path),
    )

    job = worker.run_job("target-resolver-1")

    assert job.status == "completed"
    assert job.completed_files == 2
    job_repository = JobRepository(db_path)
    try:
        jobs = job_repository.list(limit=20)
        events = job_repository.list_events("target-resolver-1")
    finally:
        job_repository.close()
    assert [item.id for item in jobs] == ["target-resolver-1"]
    assert events[-1].payload == {
        "artist_ids": ["123", "456"],
        "resolved_artist_ids": ["123", "456"],
        "resolved_from_artworks": [
            {"artwork_id": "111", "artist_id": "456", "artist_name": "Resolved Artist"},
            {"artwork_id": "222", "artist_id": "123", "artist_name": "Duplicate Artist"},
        ],
        "skipped_count": 1,
    }


def test_worker_downloads_candidate_artist_job(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    candidate_set_id = seed_candidate_download_library(db_path)
    downloader = CandidateFileDownloader(tmp_path)
    job_repository = JobRepository(db_path)
    try:
        job_repository.create(
            Job(
                id="candidate-job-1",
                type="download_candidate_artist",
                status="queued",
                input_user_id="123",
                options={
                    "candidate_set_id": candidate_set_id,
                    "conflict_mode": "overwrite",
                    "naming_rule": "{artist}/{artwork_id}_{page}.{ext}",
                },
            )
        )
    finally:
        job_repository.close()
    worker = DownloadWorker(
        db_path=db_path,
        pixiv_client_factory=FakePixivClient,
        file_downloader_factory=lambda: downloader,
    )

    job = worker.run_job("candidate-job-1")

    assert job.status == "completed"
    assert job.total_files == 1
    assert job.completed_files == 1
    assert downloader.calls == ["Artist/101_0.jpg"]
    artist_repository = ArtistRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)
    try:
        artist = artist_repository.get_by_id("123")
        files = file_repository.list_by_artwork("101")
    finally:
        artist_repository.close()
        file_repository.close()
    assert artist is not None
    assert artist.last_download_id == "101"
    assert files[0].status == "downloaded"


def seed_candidate_download_library(db_path) -> str:
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)
    candidate_repository = WorkflowCandidateRepository(db_path)
    workflow_repository = WorkflowRunRepository(db_path)
    try:
        workflow_repository.create_run(
            WorkflowRun(
                id="candidate-run-1",
                status="running",
                total=1,
                completed=0,
                failed=0,
                skipped=0,
                concurrency=1,
            )
        )
        artist_repository.upsert(Artist(id="123", name="Artist", last_download_id="100"))
        artwork_repository.upsert(
            Artwork(
                id="101",
                artist_id="123",
                title="Title",
                files=(
                    ArtworkFile(
                        artwork_id="101",
                        page_index=0,
                        original_url="https://i.pximg.net/img-original/img/101_p0.jpg",
                        file_name="101_p0.jpg",
                        status="remote_only",
                    ),
                ),
            )
        )
        file_repository.upsert(
            ArtworkFile(
                artwork_id="101",
                page_index=0,
                original_url="https://i.pximg.net/img-original/img/101_p0.jpg",
                file_name="101_p0.jpg",
                status="remote_only",
            )
        )
        candidate_set = candidate_repository.collect_artwork_candidates(
            CollectArtworkCandidatesRequest(
                workflow_run_id="candidate-run-1",
                workflow_node_run_id=None,
                artist_ids=["123"],
                source="pending_files",
                sort_order="newest_first",
                config={"collect_mode": "pending_files"},
            )
        )
        return candidate_set.id
    finally:
        workflow_repository.close()
        candidate_repository.close()
        artist_repository.close()
        artwork_repository.close()
        file_repository.close()
