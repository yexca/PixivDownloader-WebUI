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
                        latest_downloaded_artwork_id,
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
                        latest_downloaded_artwork_id = excluded.latest_downloaded_artwork_id,
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

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        query: str | None = None,
        local_tag: str | None = None,
    ) -> list[Artist]:
        sql = "SELECT DISTINCT artists.* FROM artists"
        params: list[object] = []
        where: list[str] = []
        if local_tag:
            sql += """
                JOIN artist_local_tags ON artist_local_tags.artist_id = artists.id
                JOIN local_tags ON local_tags.id = artist_local_tags.tag_id
            """
            where.append("local_tags.name = ?")
            params.append(local_tag)
        if query:
            where.append("(artists.id LIKE ? OR artists.name LIKE ?)")
            like_query = f"%{query}%"
            params.extend([like_query, like_query])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY artists.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list artists") from exc
        return [artist_from_row(row) for row in rows]

    def count(self, *, query: str | None = None, local_tag: str | None = None) -> int:
        sql = "SELECT COUNT(DISTINCT artists.id) AS total FROM artists"
        params: list[object] = []
        where: list[str] = []
        if local_tag:
            sql += """
                JOIN artist_local_tags ON artist_local_tags.artist_id = artists.id
                JOIN local_tags ON local_tags.id = artist_local_tags.tag_id
            """
            where.append("local_tags.name = ?")
            params.append(local_tag)
        if query:
            where.append("(artists.id LIKE ? OR artists.name LIKE ?)")
            like_query = f"%{query}%"
            params.extend([like_query, like_query])
        if where:
            sql += " WHERE " + " AND ".join(where)
        try:
            row = self.conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count artists") from exc
        return int(row["total"])

    def get_counts(self, artist_id: str) -> dict[str, int]:
        try:
            row = self.conn.execute(
                """
                SELECT
                    COUNT(DISTINCT artworks.id) AS artwork_count,
                    SUM(CASE WHEN artwork_files.status = 'downloaded' THEN 1 ELSE 0 END)
                        AS downloaded_file_count,
                    SUM(CASE WHEN artwork_files.status = 'remote_only' THEN 1 ELSE 0 END)
                        AS remote_file_count,
                    SUM(CASE WHEN artwork_files.status = 'pending' THEN 1 ELSE 0 END)
                        AS pending_file_count,
                    SUM(CASE WHEN artwork_files.status = 'failed' THEN 1 ELSE 0 END)
                        AS failed_file_count
                FROM artists
                LEFT JOIN artworks ON artworks.artist_id = artists.id
                LEFT JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artists.id = ?
                """,
                (artist_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to count artist aggregates for {artist_id}") from exc
        return {
            "artwork_count": int(row["artwork_count"] or 0),
            "downloaded_file_count": int(row["downloaded_file_count"] or 0),
            "remote_file_count": int(row["remote_file_count"] or 0),
            "pending_file_count": int(row["pending_file_count"] or 0),
            "failed_file_count": int(row["failed_file_count"] or 0),
        }

    def delete(self, artist_id: str) -> bool:
        try:
            with self.conn:
                artwork_rows = self.conn.execute(
                    "SELECT id FROM artworks WHERE artist_id = ?",
                    (artist_id,),
                ).fetchall()
                artwork_ids = [str(row["id"]) for row in artwork_rows]
                for artwork_id in artwork_ids:
                    self.conn.execute(
                        "DELETE FROM artwork_files WHERE artwork_id = ?",
                        (artwork_id,),
                    )
                self.conn.execute(
                    "DELETE FROM artist_local_tags WHERE artist_id = ?",
                    (artist_id,),
                )
                self.conn.execute("DELETE FROM artworks WHERE artist_id = ?", (artist_id,))
                cursor = self.conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to delete artist {artist_id}") from exc
        return cursor.rowcount > 0

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
        last_download_id=str(row["latest_downloaded_artwork_id"])
        if row["latest_downloaded_artwork_id"]
        else None,
        last_checked_at=str(row["last_checked_at"]) if row["last_checked_at"] else None,
    )
