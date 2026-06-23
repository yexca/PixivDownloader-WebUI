from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.core.paths import database_path as default_database_path
from backend.db.connection import connect
from backend.domain.entities import Artist


class LegacyArtistRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_database_path()
        self.conn = self._connect()
        self.create_table()

    def _connect(self) -> sqlite3.Connection:
        try:
            return connect(self.db_path)
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to connect to database: {self.db_path}") from exc

    def create_table(self) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pic (
                        ID TEXT PRIMARY KEY,
                        name TEXT,
                        downloadedDate TEXT,
                        lastDownloadID TEXT,
                        url TEXT
                    )
                    """
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to create legacy pic table") from exc

    def get_by_id(self, artist_id: str) -> Artist | None:
        try:
            cursor = self.conn.execute("SELECT * FROM pic WHERE ID = ?", (artist_id,))
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch artist {artist_id}") from exc

        if row is None:
            return None
        return Artist(
            id=str(row["ID"]),
            name=str(row["name"] or ""),
            profile_url=str(row["url"] or f"https://www.pixiv.net/users/{row['ID']}"),
            last_download_id=str(row["lastDownloadID"]) if row["lastDownloadID"] else None,
        )

    def upsert(self, artist: Artist, last_download_id: str | None = None) -> None:
        resolved_last_download_id = last_download_id or artist.last_download_id
        downloaded_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        profile_url = artist.profile_url or f"https://www.pixiv.net/users/{artist.id}"

        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO pic(ID, name, downloadedDate, lastDownloadID, url)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        artist.id,
                        artist.name,
                        downloaded_date,
                        resolved_last_download_id,
                        profile_url,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to upsert artist {artist.id}") from exc

    def close(self) -> None:
        self.conn.close()
