from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import Artwork
from backend.repositories._time import utc_now


class ArtworkRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def upsert(self, artwork: Artwork) -> None:
        now = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO artworks(
                        id,
                        artist_id,
                        title,
                        type,
                        caption,
                        page_count,
                        width,
                        height,
                        sanity_level,
                        restrict_value,
                        tags_json,
                        pixiv_created_at,
                        discovered_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        artist_id = excluded.artist_id,
                        title = excluded.title,
                        type = excluded.type,
                        caption = excluded.caption,
                        page_count = excluded.page_count,
                        width = excluded.width,
                        height = excluded.height,
                        sanity_level = excluded.sanity_level,
                        restrict_value = excluded.restrict_value,
                        tags_json = excluded.tags_json,
                        pixiv_created_at = excluded.pixiv_created_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        artwork.id,
                        artwork.artist_id,
                        artwork.title,
                        artwork.type,
                        artwork.caption,
                        artwork.page_count or len(artwork.files),
                        artwork.width,
                        artwork.height,
                        artwork.sanity_level,
                        artwork.restrict_value,
                        json.dumps(list(artwork.tags)),
                        artwork.pixiv_created_at,
                        now,
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to upsert artwork {artwork.id}") from exc

    def get_by_id(self, artwork_id: str) -> Artwork | None:
        try:
            row = self.conn.execute("SELECT * FROM artworks WHERE id = ?", (artwork_id,)).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch artwork {artwork_id}") from exc
        return artwork_from_row(row) if row is not None else None

    def list_by_artist(
        self,
        artist_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Artwork]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM artworks
                WHERE artist_id = ?
                ORDER BY COALESCE(pixiv_created_at, discovered_at) DESC
                LIMIT ? OFFSET ?
                """,
                (artist_id, limit, offset),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list artworks for artist {artist_id}") from exc
        return [artwork_from_row(row) for row in rows]

    def count_by_artist(self, artist_id: str) -> int:
        try:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total FROM artworks WHERE artist_id = ?",
                (artist_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to count artworks for artist {artist_id}") from exc
        return int(row["total"])

    def get_file_counts(self, artwork_id: str) -> dict[str, int]:
        try:
            row = self.conn.execute(
                """
                SELECT
                    COUNT(*) AS total_files,
                    SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END)
                        AS downloaded_files,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END)
                        AS skipped_files,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
                        AS failed_files
                FROM artwork_files
                WHERE artwork_id = ?
                """,
                (artwork_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to count files for artwork {artwork_id}") from exc
        return {
            "total_files": int(row["total_files"] or 0),
            "downloaded_files": int(row["downloaded_files"] or 0),
            "skipped_files": int(row["skipped_files"] or 0),
            "failed_files": int(row["failed_files"] or 0),
        }

    def close(self) -> None:
        self.conn.close()


def artwork_from_row(row: sqlite3.Row) -> Artwork:
    tags = tuple(str(tag) for tag in json.loads(row["tags_json"] or "[]"))
    return Artwork(
        id=str(row["id"]),
        artist_id=str(row["artist_id"]),
        title=str(row["title"] or ""),
        type=str(row["type"]) if row["type"] else None,
        caption=str(row["caption"]) if row["caption"] else None,
        page_count=int(row["page_count"]),
        width=int(row["width"]) if row["width"] is not None else None,
        height=int(row["height"]) if row["height"] is not None else None,
        sanity_level=int(row["sanity_level"]) if row["sanity_level"] is not None else None,
        restrict_value=int(row["restrict_value"]) if row["restrict_value"] is not None else None,
        tags=tags,
        pixiv_created_at=str(row["pixiv_created_at"]) if row["pixiv_created_at"] else None,
    )
