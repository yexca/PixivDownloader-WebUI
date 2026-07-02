from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


@dataclass(frozen=True)
class LegacyImport:
    id: str
    source_path: str
    status: str
    workflow_run_id: str | None = None
    total_rows: int = 0
    imported_artists: int = 0
    skipped_rows: int = 0
    last_cursor: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class LegacyImportArtist:
    import_id: str
    artist_id: str
    legacy_latest_download_id: str | None = None
    hydration_status: str = "pending"
    created_at: str | None = None
    updated_at: str | None = None


class LegacyImportRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def create(self, item: LegacyImport) -> None:
        now = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO legacy_imports(
                        id, workflow_run_id, source_path, status, total_rows,
                        imported_artists, skipped_rows, last_cursor,
                        created_at, updated_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.workflow_run_id,
                        item.source_path,
                        item.status,
                        item.total_rows,
                        item.imported_artists,
                        item.skipped_rows,
                        item.last_cursor,
                        item.created_at or now,
                        item.updated_at or now,
                        item.finished_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to create legacy import {item.id}") from exc

    def update_workflow_run_id(self, import_id: str, workflow_run_id: str) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE legacy_imports
                    SET workflow_run_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (workflow_run_id, utc_now(), import_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to link legacy import {import_id}") from exc

    def get(self, import_id: str) -> LegacyImport | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM legacy_imports WHERE id = ?",
                (import_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch legacy import {import_id}") from exc
        return legacy_import_from_row(row) if row is not None else None

    def update_progress(
        self,
        import_id: str,
        *,
        status: str,
        total_rows: int,
        imported_artists: int,
        skipped_rows: int,
        last_cursor: str | None,
        finished: bool = False,
    ) -> None:
        now = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE legacy_imports
                    SET status = ?,
                        total_rows = ?,
                        imported_artists = ?,
                        skipped_rows = ?,
                        last_cursor = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        total_rows,
                        imported_artists,
                        skipped_rows,
                        last_cursor,
                        now,
                        now if finished else None,
                        import_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update legacy import {import_id}") from exc

    def upsert_artist(
        self,
        *,
        import_id: str,
        artist_id: str,
        legacy_latest_download_id: str | None,
    ) -> None:
        now = utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO legacy_import_artists(
                        import_id, artist_id, legacy_latest_download_id,
                        hydration_status, created_at, updated_at
                    )
                    VALUES(?, ?, ?, 'pending', ?, ?)
                    ON CONFLICT(import_id, artist_id) DO UPDATE SET
                        legacy_latest_download_id = excluded.legacy_latest_download_id,
                        updated_at = excluded.updated_at
                    """,
                    (import_id, artist_id, legacy_latest_download_id, now, now),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to upsert legacy import artist {artist_id}") from exc

    def list_artists(self, import_id: str) -> list[LegacyImportArtist]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM legacy_import_artists
                WHERE import_id = ?
                ORDER BY artist_id
                """,
                (import_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list legacy import artists for {import_id}") from exc
        return [legacy_import_artist_from_row(row) for row in rows]

    def close(self) -> None:
        self.conn.close()


def legacy_import_from_row(row: sqlite3.Row) -> LegacyImport:
    return LegacyImport(
        id=str(row["id"]),
        workflow_run_id=str(row["workflow_run_id"]) if row["workflow_run_id"] else None,
        source_path=str(row["source_path"]),
        status=str(row["status"]),
        total_rows=int(row["total_rows"]),
        imported_artists=int(row["imported_artists"]),
        skipped_rows=int(row["skipped_rows"]),
        last_cursor=str(row["last_cursor"]) if row["last_cursor"] else None,
        created_at=str(row["created_at"]) if row["created_at"] else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
    )


def legacy_import_artist_from_row(row: sqlite3.Row) -> LegacyImportArtist:
    return LegacyImportArtist(
        import_id=str(row["import_id"]),
        artist_id=str(row["artist_id"]),
        legacy_latest_download_id=(
            str(row["legacy_latest_download_id"]) if row["legacy_latest_download_id"] else None
        ),
        hydration_status=str(row["hydration_status"]),
        created_at=str(row["created_at"]) if row["created_at"] else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] else None,
    )
