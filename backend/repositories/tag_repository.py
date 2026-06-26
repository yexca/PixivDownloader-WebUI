from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import LocalTag
from backend.repositories._time import utc_now


class LocalTagRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def list(self) -> list[LocalTag]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM local_tags
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list local tags") from exc
        return [LocalTag(id=int(row["id"]), name=str(row["name"])) for row in rows]

    def list_for_artist(self, artist_id: str) -> list[LocalTag]:
        try:
            rows = self.conn.execute(
                """
                SELECT local_tags.* FROM local_tags
                JOIN artist_local_tags ON artist_local_tags.tag_id = local_tags.id
                WHERE artist_local_tags.artist_id = ?
                ORDER BY local_tags.name COLLATE NOCASE
                """,
                (artist_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list local tags for artist {artist_id}") from exc
        return [LocalTag(id=int(row["id"]), name=str(row["name"])) for row in rows]

    def set_artist_tags(self, artist_id: str, tag_names: list[str]) -> list[LocalTag]:
        normalized_names = normalize_tag_names(tag_names)
        now = utc_now()
        try:
            with self.conn:
                exists = self.conn.execute(
                    "SELECT 1 FROM artists WHERE id = ?",
                    (artist_id,),
                ).fetchone()
                if exists is None:
                    raise DatabaseError(f"artist not found: {artist_id}")
                tag_ids: list[int] = []
                for name in normalized_names:
                    self.conn.execute(
                        """
                        INSERT INTO local_tags(name, created_at, updated_at)
                        VALUES(?, ?, ?)
                        ON CONFLICT(name) DO UPDATE SET updated_at = excluded.updated_at
                        """,
                        (name, now, now),
                    )
                    row = self.conn.execute(
                        "SELECT id FROM local_tags WHERE name = ?",
                        (name,),
                    ).fetchone()
                    tag_ids.append(int(row["id"]))
                self.conn.execute(
                    "DELETE FROM artist_local_tags WHERE artist_id = ?",
                    (artist_id,),
                )
                for tag_id in tag_ids:
                    self.conn.execute(
                        """
                        INSERT INTO artist_local_tags(artist_id, tag_id, created_at)
                        VALUES(?, ?, ?)
                        """,
                        (artist_id, tag_id, now),
                    )
        except DatabaseError:
            raise
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to set local tags for artist {artist_id}") from exc
        return self.list_for_artist(artist_id)

    def close(self) -> None:
        self.conn.close()


def normalize_tag_names(tag_names: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw_name in tag_names:
        name = raw_name.strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        names.append(name[:50])
        seen.add(key)
    return names
