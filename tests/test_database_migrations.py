import sqlite3

from backend.db.migrate import migrate_database


def table_names(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def test_fresh_database_migration_creates_webui_schema(tmp_path):
    db_path = tmp_path / "pixiv.db"

    applied = migrate_database(db_path, settings_json_path=tmp_path / "ignored.json")

    assert [migration.version for migration in applied] == ["001", "002", "003"]
    assert {
        "schema_migrations",
        "artists",
        "artworks",
        "artwork_files",
        "jobs",
        "job_events",
        "settings",
        "pic",
    }.issubset(table_names(db_path))


def test_legacy_pic_migration_keeps_legacy_data_and_copies_artists(tmp_path):
    db_path = tmp_path / "pixiv.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE pic (
            ID TEXT PRIMARY KEY,
            name TEXT,
            downloadedDate TEXT,
            lastDownloadID TEXT,
            url TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO pic(ID, name, downloadedDate, lastDownloadID, url)
        VALUES('123', 'Legacy Artist', '2026-06-24 01:02:03', '456', 'https://example.test/u/123')
        """
    )
    conn.commit()
    conn.close()

    migrate_database(db_path, settings_json_path=tmp_path / "missing.json")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        legacy = conn.execute("SELECT * FROM pic WHERE ID = '123'").fetchone()
        artist = conn.execute("SELECT * FROM artists WHERE id = '123'").fetchone()
    finally:
        conn.close()

    assert legacy is not None
    assert artist["name"] == "Legacy Artist"
    assert artist["profile_url"] == "https://example.test/u/123"
    assert artist["legacy_last_download_id"] == "456"
    assert artist["last_checked_at"] == "2026-06-24 01:02:03"


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "pixiv.db"

    first_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    second_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")

    conn = sqlite3.connect(db_path)
    try:
        migration_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()

    assert len(first_applied) == 3
    assert second_applied == []
    assert migration_count == 3
