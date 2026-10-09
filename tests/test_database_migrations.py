import sqlite3
from contextlib import closing

from backend.db.connection import connect
from backend.db.migrate import (
    apply_migration,
    discover_migrations,
    ensure_migration_table,
    migrate_database,
)
from backend.domain.entities import Artist, Artwork, ArtworkFile
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.artwork_repository import ArtworkRepository
from backend.repositories.file_repository import ArtworkFileRepository


def table_names(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def test_fresh_database_migration_creates_webui_schema(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"

    applied = migrate_database(db_path, settings_json_path=tmp_path / "ignored.json")

    assert [migration.version for migration in applied] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
        "007",
        "008",
        "009",
        "010",
        "011",
        "012",
        "013",
        "014",
        "015",
        "016",
        "017",
        "018",
        "019",
        "020",
        "021",
        "022",
        "023",
        "024",
    ]
    assert {
        "schema_migrations",
        "artists",
        "artworks",
        "artwork_files",
        "artwork_file_download_claims",
        "jobs",
        "job_events",
        "settings",
        "local_tags",
        "artist_local_tags",
        "workflow_runs",
        "workflow_node_runs",
        "workflow_candidate_sets",
        "workflow_candidate_artworks",
        "workflow_definitions",
        "workflow_triggers",
        "artist_name_history",
        "legacy_imports",
        "legacy_import_artists",
    }.issubset(table_names(db_path))
    assert "pic" not in table_names(db_path)


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"

    first_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    second_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")

    conn = sqlite3.connect(db_path)
    try:
        migration_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()

    assert len(first_applied) == 24
    assert second_applied == []
    assert migration_count == 24


def test_integrity_upgrade_preserves_existing_download_data(tmp_path):
    db_path = tmp_path / "existing.sqlite3"
    with closing(connect(db_path)) as conn:
        ensure_migration_table(conn)
        for migration in discover_migrations():
            if migration.version < "024":
                apply_migration(conn, migration)
    with (
        closing(ArtistRepository(db_path)) as artists,
        closing(ArtworkRepository(db_path)) as artworks,
        closing(ArtworkFileRepository(db_path)) as files,
    ):
        artists.upsert(Artist(id="1", name="Existing", last_download_id="100"))
        artworks.upsert(Artwork(id="100", artist_id="1", page_count=1))
        file_id = files.upsert(
            ArtworkFile(
                artwork_id="100",
                page_index=0,
                original_url="https://example.test/100.jpg",
                file_name="100.jpg",
                status="downloaded",
                local_path=tmp_path / "100.jpg",
                size_bytes=20,
                downloaded_at="2026-01-01T00:00:00Z",
            )
        )
        original_artist = artists.get_by_id("1")
        original_file = files.get_by_id(file_id)
        assert [item.version for item in migrate_database(db_path)] == ["024"]
        assert artists.get_by_id("1") == original_artist
        assert files.get_by_id(file_id) == original_file
        assert artists.get_metadata_sync_watermark("1") is None
        assert (
            files.conn.execute("SELECT COUNT(*) FROM artwork_file_download_claims").fetchone()[0]
            == 0
        )
