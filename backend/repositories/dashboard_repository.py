from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect


class DashboardRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def library_counts(self) -> dict[str, int]:
        try:
            artist_row = self.conn.execute("SELECT COUNT(*) AS total FROM artists").fetchone()
            artwork_row = self.conn.execute("SELECT COUNT(*) AS total FROM artworks").fetchone()
            file_rows = self.conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM artwork_files
                GROUP BY status
                """
            ).fetchall()
            attention_row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM artists
                WHERE account_status = 'unavailable'
                   OR (
                        remote_latest_artwork_id IS NOT NULL
                        AND CAST(remote_latest_artwork_id AS INTEGER) >
                            CAST(COALESCE(latest_downloaded_artwork_id, '0') AS INTEGER)
                   )
                   OR EXISTS (
                        SELECT 1 FROM artworks
                        JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                        WHERE artworks.artist_id = artists.id
                          AND artwork_files.status = 'failed'
                   )
                """
            ).fetchone()
            updates_row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM artists
                WHERE remote_latest_artwork_id IS NOT NULL
                  AND CAST(remote_latest_artwork_id AS INTEGER) >
                      CAST(COALESCE(latest_downloaded_artwork_id, '0') AS INTEGER)
                """
            ).fetchone()
            failed_artist_row = self.conn.execute(
                """
                SELECT COUNT(DISTINCT artworks.artist_id) AS total
                FROM artworks
                JOIN artwork_files ON artwork_files.artwork_id = artworks.id
                WHERE artwork_files.status = 'failed'
                """
            ).fetchone()
            unavailable_row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM artists
                WHERE account_status = 'unavailable'
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to fetch dashboard library counts") from exc

        file_counts = {str(row["status"]): int(row["total"]) for row in file_rows}
        return {
            "artists": int(artist_row["total"] if artist_row else 0),
            "artworks": int(artwork_row["total"] if artwork_row else 0),
            "downloaded_files": file_counts.get("downloaded", 0),
            "pending_files": file_counts.get("pending", 0) + file_counts.get("remote_only", 0),
            "failed_files": file_counts.get("failed", 0),
            "attention_artists": int(attention_row["total"] if attention_row else 0),
            "artists_with_updates": int(updates_row["total"] if updates_row else 0),
            "artists_with_failed_files": int(
                failed_artist_row["total"] if failed_artist_row else 0
            ),
            "unavailable_artists": int(unavailable_row["total"] if unavailable_row else 0),
        }

    def workflow_counts(self) -> dict[str, int]:
        try:
            run_rows = self.conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM workflow_runs
                GROUP BY status
                """
            ).fetchall()
            schedule_rows = self.conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM workflow_triggers
                GROUP BY status
                """
            ).fetchall()
            waiting_row = self.conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM jobs
                WHERE status = 'inactive'
                  AND json_extract(options_json, '$.activation_scope') = 'one_time'
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to fetch dashboard workflow counts") from exc

        run_counts = {str(row["status"]): int(row["total"]) for row in run_rows}
        schedule_counts = {str(row["status"]): int(row["total"]) for row in schedule_rows}
        return {
            "running_runs": run_counts.get("running", 0),
            "failed_runs": run_counts.get("failed", 0) + run_counts.get("partial", 0),
            "completed_runs": run_counts.get("completed", 0) + run_counts.get("skipped", 0),
            "active_schedules": schedule_counts.get("active", 0),
            "blocked_schedules": schedule_counts.get("blocked", 0),
            "inactive_schedules": schedule_counts.get("inactive", 0)
            + schedule_counts.get("paused", 0),
            "waiting_jobs": int(waiting_row["total"] if waiting_row else 0),
        }

    def job_counts(self) -> dict[str, int]:
        try:
            rows = self.conn.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM jobs
                GROUP BY status
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to fetch dashboard job counts") from exc
        counts = {str(row["status"]): int(row["total"]) for row in rows}
        return {
            "inactive": counts.get("inactive", 0),
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
        }

    def close(self) -> None:
        self.conn.close()
