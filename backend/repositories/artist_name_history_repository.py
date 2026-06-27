from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import ArtistNameHistory
from backend.repositories._time import utc_now


class ArtistNameHistoryRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def record_name(self, artist_id: str, name: str, *, source: str = "pixiv") -> None:
        normalized_name = name.strip()
        if not normalized_name:
            return
        now = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO artist_name_history(
                        artist_id,
                        name,
                        source,
                        first_seen_at,
                        last_seen_at
                    )
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(artist_id, name) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at,
                        source = excluded.source
                    """,
                    (artist_id, normalized_name, source, now, now),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to record artist name history for {artist_id}") from exc

    def list_for_artist(self, artist_id: str) -> list[ArtistNameHistory]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM artist_name_history
                WHERE artist_id = ?
                ORDER BY last_seen_at DESC, id DESC
                """,
                (artist_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list artist name history for {artist_id}") from exc
        return [artist_name_history_from_row(row) for row in rows]

    def close(self) -> None:
        self.conn.close()


def artist_name_history_from_row(row: sqlite3.Row) -> ArtistNameHistory:
    return ArtistNameHistory(
        id=int(row["id"]),
        artist_id=str(row["artist_id"]),
        name=str(row["name"]),
        source=str(row["source"]),
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
    )
