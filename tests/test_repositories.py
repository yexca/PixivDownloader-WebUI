from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job, JobEvent
from backend.repositories import (
    ArtistNameHistoryRepository,
    ArtistRepository,
    ArtworkFileRepository,
    ArtworkRepository,
    JobRepository,
    LocalTagRepository,
    SettingsRepository,
)


def test_artist_repository_crud(tmp_path):
    db_path = migrated_db(tmp_path)
    repository = ArtistRepository(db_path)

    repository.upsert(
        Artist(
            id="123",
            name="Artist",
            profile_url="https://www.pixiv.net/users/123",
            last_download_id="456",
        )
    )

    artist = repository.get_by_id("123")
    assert artist is not None
    assert artist.name == "Artist"
    assert artist.last_download_id == "456"
    assert repository.count() == 1
    assert repository.list(query="Art")[0].id == "123"


def test_artist_repository_filters_update_and_account_status(tmp_path):
    db_path = migrated_db(tmp_path)
    repository = ArtistRepository(db_path)

    repository.upsert(
        Artist(
            id="123",
            name="Needs Update",
            last_download_id="100",
            account_status="available",
            remote_latest_artwork_id="200",
            remote_latest_checked_at="2023-01-01T00:00:00Z",
        )
    )
    repository.upsert(
        Artist(
            id="456",
            name="Closed",
            account_status="unavailable",
            account_status_reason="Page not found",
            remote_latest_checked_at="2999-01-01T00:00:00Z",
        )
    )

    assert [artist.id for artist in repository.list(update_state="available")] == ["123"]
    assert [artist.id for artist in repository.list(account_status="unavailable")] == ["456"]
    assert repository.count(update_state="attention", stale_days=30) == 2


def test_artist_name_history_repository_records_seen_names(tmp_path):
    db_path = migrated_db(tmp_path)
    ArtistRepository(db_path).upsert(Artist(id="123", name="Current"))
    repository = ArtistNameHistoryRepository(db_path)

    repository.record_name("123", "Old Name")
    repository.record_name("123", "Old Name")
    repository.record_name("123", "Current")

    names = repository.list_for_artist("123")
    assert {item.name for item in names} == {"Old Name", "Current"}
    assert len(names) == 2


def test_artwork_and_file_repositories_crud(tmp_path):
    db_path = migrated_db(tmp_path)
    ArtistRepository(db_path).upsert(
        Artist(id="123", name="Artist", profile_url="https://www.pixiv.net/users/123")
    )
    artwork_repository = ArtworkRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)

    artwork_repository.upsert(
        Artwork(
            id="999",
            artist_id="123",
            title="Title",
            page_count=1,
            tags=("tag-a", "tag-b"),
        )
    )
    file_id = file_repository.upsert(
        ArtworkFile(
            artwork_id="999",
            page_index=0,
            original_url="https://i.pximg.net/img-original/img/999_p0.jpg",
            file_name="999_p0.jpg",
            status="downloaded",
            local_path=tmp_path / "999_p0.jpg",
            size_bytes=1234,
        )
    )

    artwork = artwork_repository.get_by_id("999")
    files = file_repository.list_by_artwork("999")

    assert artwork is not None
    assert artwork.tags == ("tag-a", "tag-b")
    assert artwork_repository.list_by_artist("123")[0].id == "999"
    assert files[0].id == file_id
    assert files[0].status == "downloaded"
    assert file_repository.get_by_id(file_id).file_name == "999_p0.jpg"


def test_artist_delete_removes_library_records_only(tmp_path):
    db_path = migrated_db(tmp_path)
    artist_repository = ArtistRepository(db_path)
    artwork_repository = ArtworkRepository(db_path)
    file_repository = ArtworkFileRepository(db_path)
    artist_repository.upsert(Artist(id="123", name="Artist"))
    artwork_repository.upsert(Artwork(id="999", artist_id="123", title="Title"))
    file_id = file_repository.upsert(
        ArtworkFile(
            artwork_id="999",
            page_index=0,
            original_url="https://i.pximg.net/img-original/img/999_p0.jpg",
            file_name="999_p0.jpg",
            status="downloaded",
            local_path=tmp_path / "999_p0.jpg",
        )
    )

    assert artist_repository.delete("123") is True

    assert artist_repository.get_by_id("123") is None
    assert artwork_repository.get_by_id("999") is None
    assert file_repository.get_by_id(file_id) is None


def test_local_tag_repository_sets_and_filters_artist_tags(tmp_path):
    db_path = migrated_db(tmp_path)
    artist_repository = ArtistRepository(db_path)
    tag_repository = LocalTagRepository(db_path)
    artist_repository.upsert(Artist(id="123", name="Artist"))
    artist_repository.upsert(Artist(id="456", name="Other"))

    tags = tag_repository.set_artist_tags("123", ["favorite", " reference ", "favorite"])

    assert [tag.name for tag in tags] == ["favorite", "reference"]
    assert [artist.id for artist in artist_repository.list(local_tag="favorite")] == ["123"]
    assert artist_repository.count(local_tag="favorite") == 1


def test_job_repository_crud(tmp_path):
    db_path = migrated_db(tmp_path)
    repository = JobRepository(db_path)

    repository.create(Job(id="job-1", type="download_artist", status="queued", input_user_id="123"))
    repository.update(
        Job(
            id="job-1",
            type="download_artist",
            status="running",
            input_user_id="123",
            artist_id="123",
            total_files=2,
            completed_files=1,
        )
    )
    event_id = repository.add_event(
        JobEvent(job_id="job-1", level="info", message="Downloading", payload={"file": "a.jpg"})
    )

    job = repository.get_by_id("job-1")
    events = repository.list_events("job-1")

    assert job is not None
    assert job.status == "running"
    assert job.completed_files == 1
    assert repository.list(status="running")[0].id == "job-1"
    assert events[0].id == event_id
    assert events[0].payload == {"file": "a.jpg"}


def test_job_repository_requeues_running_jobs(tmp_path):
    db_path = migrated_db(tmp_path)
    repository = JobRepository(db_path)

    repository.create(Job(id="running-job", type="download_artist", status="queued"))
    repository.create(Job(id="queued-job", type="download_artist", status="queued"))
    running = repository.get_by_id("running-job")
    assert running is not None
    repository.update(
        Job(
            id=running.id,
            type=running.type,
            status="running",
            total_files=10,
            completed_files=4,
            skipped_files=1,
            failed_files=1,
            started_at="2026-06-28T00:00:00Z",
        )
    )

    jobs = repository.requeue_running()

    recovered = repository.get_by_id("running-job")
    queued = repository.get_by_id("queued-job")
    assert [job.id for job in jobs] == ["running-job"]
    assert recovered.status == "queued"
    assert recovered.total_files == 0
    assert recovered.completed_files == 0
    assert recovered.skipped_files == 0
    assert recovered.failed_files == 0
    assert recovered.started_at is None
    assert queued.status == "queued"


def test_settings_repository_crud(tmp_path):
    db_path = migrated_db(tmp_path)
    repository = SettingsRepository(db_path)

    repository.set("skip_existing_files", True)
    repository.set("max_concurrent_downloads", 3)

    assert repository.get("skip_existing_files") is True
    assert repository.get("max_concurrent_downloads") == 3
    assert repository.get("missing", "fallback") == "fallback"
    assert repository.all()["skip_existing_files"] is True


def migrated_db(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    return db_path
