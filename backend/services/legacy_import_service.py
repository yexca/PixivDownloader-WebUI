from __future__ import annotations

import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.domain.entities import Artist
from backend.repositories.artist_repository import ArtistRepository
from backend.repositories.legacy_import_repository import (
    LegacyImportRepository,
)


@dataclass(frozen=True)
class LegacyDatabaseImportSummary:
    imported_artists: int
    skipped_rows: int
    total_rows: int
    imported_artist_ids: tuple[str, ...] = ()
    legacy_latest_download_id_by_artist: dict[str, str | None] | None = None


class LegacyDatabaseImportService:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path

    def import_file(self, file_obj) -> LegacyDatabaseImportSummary:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
            temp_path = Path(temp_file.name)
            shutil.copyfileobj(file_obj, temp_file)
        try:
            return self.import_path(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def import_path(self, legacy_db_path: Path | str) -> LegacyDatabaseImportSummary:
        legacy_path = Path(legacy_db_path)
        rows = self._read_legacy_rows(legacy_path)
        repository = ArtistRepository(self.db_path)
        imported = 0
        skipped = 0
        imported_artist_ids: list[str] = []
        legacy_latest_download_id_by_artist: dict[str, str | None] = {}
        try:
            for row in rows:
                artist = legacy_row_to_artist(row)
                if artist is None:
                    skipped += 1
                    continue
                repository.upsert(artist)
                imported_artist_ids.append(artist.id)
                legacy_latest_download_id_by_artist[artist.id] = artist.last_download_id
                imported += 1
        finally:
            repository.close()
        return LegacyDatabaseImportSummary(
            imported_artists=imported,
            skipped_rows=skipped,
            total_rows=len(rows),
            imported_artist_ids=tuple(imported_artist_ids),
            legacy_latest_download_id_by_artist=legacy_latest_download_id_by_artist,
        )

    def scan_import(
        self,
        import_id: str,
        *,
        batch_size: int = 500,
    ) -> LegacyDatabaseImportSummary:
        legacy_repository = LegacyImportRepository(self.db_path)
        artist_repository = ArtistRepository(self.db_path)
        imported_artist_ids: list[str] = []
        legacy_latest_download_id_by_artist: dict[str, str | None] = {}
        try:
            item = legacy_repository.get(import_id)
            if item is None:
                raise DatabaseError(f"legacy import was not found: {import_id}")
            total_rows = item.total_rows or self._count_legacy_rows(Path(item.source_path))
            imported = item.imported_artists
            skipped = item.skipped_rows
            last_cursor = item.last_cursor
            legacy_repository.update_progress(
                import_id,
                status="running",
                total_rows=total_rows,
                imported_artists=imported,
                skipped_rows=skipped,
                last_cursor=last_cursor,
            )
            while True:
                rows = self._read_legacy_rows_page(
                    Path(item.source_path),
                    after_id=last_cursor,
                    limit=batch_size,
                )
                if not rows:
                    break
                for row in rows:
                    last_cursor = str(row["ID"] or "")
                    artist = legacy_row_to_artist(row)
                    if artist is None:
                        skipped += 1
                        continue
                    artist_repository.upsert(artist)
                    legacy_repository.upsert_artist(
                        import_id=import_id,
                        artist_id=artist.id,
                        legacy_latest_download_id=artist.last_download_id,
                    )
                    imported_artist_ids.append(artist.id)
                    legacy_latest_download_id_by_artist[artist.id] = artist.last_download_id
                    imported += 1
                legacy_repository.update_progress(
                    import_id,
                    status="running",
                    total_rows=total_rows,
                    imported_artists=imported,
                    skipped_rows=skipped,
                    last_cursor=last_cursor,
                )
            legacy_repository.update_progress(
                import_id,
                status="completed",
                total_rows=total_rows,
                imported_artists=imported,
                skipped_rows=skipped,
                last_cursor=last_cursor,
                finished=True,
            )
            return LegacyDatabaseImportSummary(
                imported_artists=imported,
                skipped_rows=skipped,
                total_rows=total_rows,
                imported_artist_ids=tuple(imported_artist_ids),
                legacy_latest_download_id_by_artist=legacy_latest_download_id_by_artist,
            )
        finally:
            artist_repository.close()
            legacy_repository.close()

    def _read_legacy_rows(self, legacy_db_path: Path) -> list[sqlite3.Row]:
        try:
            conn = sqlite3.connect(legacy_db_path)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise DatabaseError("legacy database could not be opened") from exc

        try:
            if not _has_legacy_pic_table(conn):
                raise DatabaseError("legacy database does not contain a pic table")
            rows = conn.execute(
                """
                SELECT ID, name, downloadedDate, lastDownloadID, url
                FROM pic
                ORDER BY ID
                """
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            if isinstance(exc, DatabaseError):
                raise
            raise DatabaseError("legacy database could not be read") from exc
        finally:
            conn.close()
        return rows

    def _read_legacy_rows_page(
        self,
        legacy_db_path: Path,
        *,
        after_id: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        try:
            conn = sqlite3.connect(legacy_db_path)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise DatabaseError("legacy database could not be opened") from exc

        try:
            if not _has_legacy_pic_table(conn):
                raise DatabaseError("legacy database does not contain a pic table")
            if after_id is None:
                rows = conn.execute(
                    """
                    SELECT ID, name, downloadedDate, lastDownloadID, url
                    FROM pic
                    ORDER BY ID
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT ID, name, downloadedDate, lastDownloadID, url
                    FROM pic
                    WHERE ID > ?
                    ORDER BY ID
                    LIMIT ?
                    """,
                    (after_id, limit),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            if isinstance(exc, DatabaseError):
                raise
            raise DatabaseError("legacy database could not be read") from exc
        finally:
            conn.close()
        return rows

    def _count_legacy_rows(self, legacy_db_path: Path) -> int:
        try:
            conn = sqlite3.connect(legacy_db_path)
        except sqlite3.Error as exc:
            raise DatabaseError("legacy database could not be opened") from exc

        try:
            if not _has_legacy_pic_table(conn):
                raise DatabaseError("legacy database does not contain a pic table")
            row = conn.execute("SELECT COUNT(*) FROM pic").fetchone()
        except sqlite3.DatabaseError as exc:
            if isinstance(exc, DatabaseError):
                raise
            raise DatabaseError("legacy database could not be read") from exc
        finally:
            conn.close()
        return int(row[0] if row is not None else 0)


def _has_legacy_pic_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'pic'
        """
    ).fetchone()
    return row is not None


def legacy_row_to_artist(row: sqlite3.Row) -> Artist | None:
    artist_id = str(row["ID"] or "").strip()
    if not artist_id:
        return None
    name = str(row["name"] or "").strip() or artist_id
    profile_url = str(row["url"] or "").strip() or f"https://www.pixiv.net/users/{artist_id}"
    latest_downloaded_artwork_id = str(row["lastDownloadID"] or "").strip() or None
    last_checked_at = str(row["downloadedDate"] or "").strip() or None
    return Artist(
        id=artist_id,
        name=name,
        profile_url=profile_url,
        last_download_id=latest_downloaded_artwork_id,
        last_checked_at=last_checked_at,
    )
