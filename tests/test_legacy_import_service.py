import sqlite3

from backend.db.migrate import migrate_database
from backend.repositories.artist_repository import ArtistRepository
from backend.services.legacy_import_service import LegacyDatabaseImportService


def test_import_legacy_database(tmp_path):
    target_db = tmp_path / "pixiv.sqlite3"
    legacy_db = tmp_path / "pixiv.db"
    create_legacy_database(legacy_db)
    migrate_database(target_db)

    summary = LegacyDatabaseImportService(target_db).import_path(legacy_db)

    repository = ArtistRepository(target_db)
    try:
        artist = repository.get_by_id("100058387")
    finally:
        repository.close()

    assert summary.total_rows == 2
    assert summary.imported_artists == 2
    assert summary.skipped_rows == 0
    assert artist is not None
    assert artist.name == "Legacy Artist"
    assert artist.last_download_id == "113381074"


def create_legacy_database(db_path):
    conn = sqlite3.connect(db_path)
    try:
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
        conn.executemany(
            """
            INSERT INTO pic(ID, name, downloadedDate, lastDownloadID, url)
            VALUES(?, ?, ?, ?, ?)
            """,
            [
                (
                    "100058387",
                    "Legacy Artist",
                    "2023-11-13 00:00:00",
                    "113381074",
                    "https://www.pixiv.net/users/100058387",
                ),
                (
                    "101013492",
                    "Second Artist",
                    "2025-01-05 23:52:11",
                    "125619677",
                    "https://www.pixiv.net/users/101013492",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()
