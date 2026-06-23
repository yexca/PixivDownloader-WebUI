from backend.db.migrate import migrate_database
from backend.domain.entities import Artist, Artwork, ArtworkFile, Job, JobEvent
from backend.repositories import (
    ArtistRepository,
    ArtworkFileRepository,
    ArtworkRepository,
    JobRepository,
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
    db_path = tmp_path / "pixiv.db"
    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    return db_path
