from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import ArtworkFile
from backend.repositories._time import utc_now


class ArtworkFileRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def upsert(self, file: ArtworkFile) -> int:
        now = utc_now()
        local_path = str(file.local_path) if file.local_path is not None else None
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO artwork_files(
                        artwork_id,
                        page_index,
                        original_url,
                        local_path,
                        file_name,
                        size_bytes,
                        status,
                        downloaded_at,
                        error_message,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(artwork_id, page_index) DO UPDATE SET
                        original_url = excluded.original_url,
                        local_path = excluded.local_path,
                        file_name = excluded.file_name,
                        size_bytes = excluded.size_bytes,
                        status = excluded.status,
                        downloaded_at = excluded.downloaded_at,
                        error_message = excluded.error_message,
                        updated_at = excluded.updated_at
                    """,
                    (
                        file.artwork_id,
                        file.page_index,
                        file.original_url,
                        local_path,
                        file.file_name,
                        file.size_bytes,
                        file.status,
                        file.downloaded_at,
                        file.error_message,
                        now,
                        now,
                    ),
                )
                row = self.conn.execute(
                    """
                    SELECT id FROM artwork_files
                    WHERE artwork_id = ? AND page_index = ?
                    """,
                    (file.artwork_id, file.page_index),
                ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to upsert artwork file {file.file_name}") from exc
        return int(row["id"])

    def list_by_artwork(self, artwork_id: str) -> list[ArtworkFile]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM artwork_files
                WHERE artwork_id = ?
                ORDER BY page_index
                """,
                (artwork_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list files for artwork {artwork_id}") from exc
        return [artwork_file_from_row(row) for row in rows]

    def get_by_id(self, file_id: int) -> ArtworkFile | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM artwork_files WHERE id = ?", (file_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch artwork file {file_id}") from exc
        return artwork_file_from_row(row) if row is not None else None

    def update_status(
        self,
        file_id: int,
        *,
        status: str,
        local_path: Path | str | None = None,
        size_bytes: int | None = None,
        downloaded_at: str | None = None,
        error_message: str | None = None,
    ) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE artwork_files
                    SET status = ?,
                        local_path = COALESCE(?, local_path),
                        size_bytes = COALESCE(?, size_bytes),
                        downloaded_at = COALESCE(?, downloaded_at),
                        error_message = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        str(local_path) if local_path is not None else None,
                        size_bytes,
                        downloaded_at,
                        error_message,
                        utc_now(),
                        file_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update artwork file {file_id}") from exc

    def list_failed(self, *, limit: int = 100) -> list[ArtworkFile]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM artwork_files
                WHERE status = 'failed'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list failed artwork files") from exc
        return [artwork_file_from_row(row) for row in rows]

    def close(self) -> None:
        self.conn.close()


def artwork_file_from_row(row: sqlite3.Row) -> ArtworkFile:
    return ArtworkFile(
        id=int(row["id"]),
        artwork_id=str(row["artwork_id"]),
        page_index=int(row["page_index"]),
        original_url=str(row["original_url"]),
        local_path=Path(str(row["local_path"])) if row["local_path"] else None,
        file_name=str(row["file_name"]),
        size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        status=row["status"],
        downloaded_at=str(row["downloaded_at"]) if row["downloaded_at"] else None,
        error_message=str(row["error_message"]) if row["error_message"] else None,
    )
