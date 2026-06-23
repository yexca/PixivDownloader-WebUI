from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import Artist
from backend.repositories._time import utc_now


class ArtistRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def upsert(self, artist: Artist) -> None:
        now = utc_now()
        profile_url = artist.profile_url or f"https://www.pixiv.net/users/{artist.id}"
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO artists(
                        id,
                        name,
                        account,
                        profile_url,
                        avatar_url,
                        comment,
                        legacy_last_download_id,
                        last_checked_at,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        account = excluded.account,
                        profile_url = excluded.profile_url,
                        avatar_url = excluded.avatar_url,
                        comment = excluded.comment,
                        legacy_last_download_id = excluded.legacy_last_download_id,
                        last_checked_at = excluded.last_checked_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        artist.id,
                        artist.name,
                        artist.account,
                        profile_url,
                        artist.avatar_url,
                        artist.comment,
                        artist.last_download_id,
                        artist.last_checked_at or now,
                        now,
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to upsert artist {artist.id}") from exc

    def get_by_id(self, artist_id: str) -> Artist | None:
        try:
            row = self.conn.execute("SELECT * FROM artists WHERE id = ?", (artist_id,)).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch artist {artist_id}") from exc

        return artist_from_row(row) if row is not None else None

    def list(self, *, limit: int = 50, offset: int = 0, query: str | None = None) -> list[Artist]:
        sql = "SELECT * FROM artists"
        params: list[object] = []
        if query:
            sql += " WHERE id LIKE ? OR name LIKE ?"
            like_query = f"%{query}%"
            params.extend([like_query, like_query])
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list artists") from exc
        return [artist_from_row(row) for row in rows]

    def count(self) -> int:
        try:
            row = self.conn.execute("SELECT COUNT(*) AS total FROM artists").fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count artists") from exc
        return int(row["total"])

    def close(self) -> None:
        self.conn.close()


def artist_from_row(row: sqlite3.Row) -> Artist:
    return Artist(
        id=str(row["id"]),
        name=str(row["name"]),
        profile_url=str(row["profile_url"]),
        account=str(row["account"]) if row["account"] else None,
        avatar_url=str(row["avatar_url"]) if row["avatar_url"] else None,
        comment=str(row["comment"]) if row["comment"] else None,
        last_download_id=str(row["legacy_last_download_id"])
        if row["legacy_last_download_id"]
        else None,
        last_checked_at=str(row["last_checked_at"]) if row["last_checked_at"] else None,
    )
