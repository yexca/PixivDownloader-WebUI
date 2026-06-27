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
                        account_status,
                        account_status_checked_at,
                        account_status_reason,
                        remote_latest_artwork_id,
                        remote_latest_checked_at,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        account = excluded.account,
                        profile_url = excluded.profile_url,
                        avatar_url = excluded.avatar_url,
                        comment = excluded.comment,
                        latest_downloaded_artwork_id = excluded.latest_downloaded_artwork_id,
                        last_checked_at = excluded.last_checked_at,
                        account_status = excluded.account_status,
                        account_status_checked_at = excluded.account_status_checked_at,
                        account_status_reason = excluded.account_status_reason,
                        remote_latest_artwork_id = excluded.remote_latest_artwork_id,
                        remote_latest_checked_at = excluded.remote_latest_checked_at,
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
                        artist.account_status,
                        artist.account_status_checked_at,
                        artist.account_status_reason,
                        artist.remote_latest_artwork_id,
                        artist.remote_latest_checked_at,
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
        file_state: str | None = None,
        tag_state: str | None = None,
        account_status: str | None = None,
        update_state: str | None = None,
        stale_days: int | None = None,
        sort: str = "updated_desc",
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
        add_artist_filters(
            where,
            params,
            tag_state=tag_state,
            file_state=file_state,
            account_status=account_status,
            update_state=update_state,
            stale_days=stale_days,
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {artist_sort_expression(sort)} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list artists") from exc
        return [artist_from_row(row) for row in rows]

    def count(
        self,
        *,
        query: str | None = None,
        local_tag: str | None = None,
        file_state: str | None = None,
        tag_state: str | None = None,
        account_status: str | None = None,
        update_state: str | None = None,
        stale_days: int | None = None,
    ) -> int:
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
        add_artist_filters(
            where,
            params,
            tag_state=tag_state,
            file_state=file_state,
            account_status=account_status,
            update_state=update_state,
            stale_days=stale_days,
        )
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
        account_status=row["account_status"],
        account_status_checked_at=str(row["account_status_checked_at"])
        if row["account_status_checked_at"]
        else None,
        account_status_reason=str(row["account_status_reason"])
        if row["account_status_reason"]
        else None,
        remote_latest_artwork_id=str(row["remote_latest_artwork_id"])
        if row["remote_latest_artwork_id"]
        else None,
        remote_latest_checked_at=str(row["remote_latest_checked_at"])
        if row["remote_latest_checked_at"]
        else None,
    )


def add_artist_filters(
    where: list[str],
    params: list[object],
    *,
    tag_state: str | None,
    file_state: str | None,
    account_status: str | None,
    update_state: str | None,
    stale_days: int | None,
) -> None:
    if tag_state == "untagged":
        where.append(
            """
            NOT EXISTS (
                SELECT 1 FROM artist_local_tags
                WHERE artist_local_tags.artist_id = artists.id
            )
            """
        )
    if tag_state == "tagged":
        where.append(
            """
            EXISTS (
                SELECT 1 FROM artist_local_tags
                WHERE artist_local_tags.artist_id = artists.id
            )
            """
        )
    if file_state == "failed":
        where.append(status_exists("failed"))
    if file_state == "pending":
        where.append(status_exists("pending", "remote_only"))
    if file_state == "downloaded":
        where.append(
            """
            EXISTS (
                SELECT 1 FROM artworks
                JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artworks.artist_id = artists.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM artworks
                JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artworks.artist_id = artists.id
                  AND artwork_files.status NOT IN ('downloaded', 'skipped')
            )
            """
        )
    if account_status in {"unknown", "available", "unavailable"}:
        where.append("artists.account_status = ?")
        params.append(account_status)
    if update_state == "available":
        where.append(artist_has_remote_update())
    if update_state == "stale":
        where.append(artist_is_stale_sql(stale_days or 30))
    if update_state == "attention":
        where.append(
            f"""
            (
                artists.account_status = 'unavailable'
                OR {artist_has_remote_update()}
                OR {artist_is_stale_sql(stale_days or 30)}
                OR {status_exists("failed")}
            )
            """
        )


def status_exists(*statuses: str) -> str:
    quoted_statuses = ", ".join(f"'{status}'" for status in statuses)
    return f"""
        EXISTS (
            SELECT 1 FROM artworks
            JOIN artwork_files ON artwork_files.artwork_id = artworks.id
            WHERE artworks.artist_id = artists.id
              AND artwork_files.status IN ({quoted_statuses})
        )
    """


def artist_sort_expression(sort: str) -> str:
    if sort == "name_asc":
        return "LOWER(artists.name) ASC, artists.id ASC"
    if sort == "id_asc":
        return "artists.id ASC"
    if sort == "failed_desc":
        return """
            (
                SELECT COUNT(*) FROM artworks
                JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artworks.artist_id = artists.id
                  AND artwork_files.status = 'failed'
            ) DESC,
            artists.updated_at DESC
        """
    if sort == "pending_desc":
        return """
            (
                SELECT COUNT(*) FROM artworks
                JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artworks.artist_id = artists.id
                  AND artwork_files.status IN ('pending', 'remote_only')
            ) DESC,
            artists.updated_at DESC
        """
    if sort == "checked_asc":
        return "artists.last_checked_at IS NOT NULL ASC, artists.last_checked_at ASC"
    if sort == "attention_desc":
        return """
            CASE WHEN artists.account_status = 'unavailable' THEN 1 ELSE 0 END DESC,
            CASE WHEN (
                artists.remote_latest_artwork_id IS NOT NULL
                AND CAST(artists.remote_latest_artwork_id AS INTEGER) >
                    CAST(COALESCE(artists.latest_downloaded_artwork_id, '0') AS INTEGER)
            ) THEN 1 ELSE 0 END DESC,
            artists.remote_latest_checked_at IS NOT NULL ASC,
            artists.remote_latest_checked_at ASC,
            artists.updated_at DESC
        """
    if sort == "remote_checked_asc":
        return (
            "artists.remote_latest_checked_at IS NOT NULL ASC, artists.remote_latest_checked_at ASC"
        )
    return "artists.updated_at DESC"


def artist_has_remote_update() -> str:
    return """
        artists.remote_latest_artwork_id IS NOT NULL
        AND CAST(artists.remote_latest_artwork_id AS INTEGER) >
            CAST(COALESCE(artists.latest_downloaded_artwork_id, '0') AS INTEGER)
    """


def artist_is_stale_sql(days: int) -> str:
    safe_days = max(1, int(days))
    return f"""
        (
            artists.remote_latest_checked_at IS NULL
            OR datetime(replace(artists.remote_latest_checked_at, 'Z', '+00:00')) <=
                datetime('now', '-{safe_days} days')
        )
    """
