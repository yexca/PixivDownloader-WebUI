from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import Job, JobEvent
from backend.repositories._time import utc_now


class JobRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def create(self, job: Job) -> None:
        created_at = job.created_at or utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO jobs(
                        id,
                        type,
                        status,
                        input_user_id,
                        input_artwork_id,
                        artist_id,
                        total_files,
                        completed_files,
                        skipped_files,
                        failed_files,
                        cancel_requested,
                        error_message,
                        created_at,
                        started_at,
                        finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.type,
                        job.status,
                        job.input_user_id,
                        job.input_artwork_id,
                        job.artist_id,
                        job.total_files,
                        job.completed_files,
                        job.skipped_files,
                        job.failed_files,
                        int(job.cancel_requested),
                        job.error_message,
                        created_at,
                        job.started_at,
                        job.finished_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to create job {job.id}") from exc

    def get_by_id(self, job_id: str) -> Job | None:
        try:
            row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch job {job_id}") from exc
        return job_from_row(row) if row is not None else None

    def update(self, job: Job) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?,
                        artist_id = ?,
                        total_files = ?,
                        completed_files = ?,
                        skipped_files = ?,
                        failed_files = ?,
                        cancel_requested = ?,
                        error_message = ?,
                        started_at = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        job.status,
                        job.artist_id,
                        job.total_files,
                        job.completed_files,
                        job.skipped_files,
                        job.failed_files,
                        int(job.cancel_requested),
                        job.error_message,
                        job.started_at,
                        job.finished_at,
                        job.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update job {job.id}") from exc

    def request_cancel(self, job_id: str) -> Job | None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE jobs
                    SET cancel_requested = 1
                    WHERE id = ?
                    """,
                    (job_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to request cancellation for job {job_id}") from exc
        return self.get_by_id(job_id)

    def next_queued(self) -> Job | None:
        try:
            row = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to fetch next queued job") from exc
        return job_from_row(row) if row is not None else None

    def list(self, *, status: str | None = None, limit: int = 50, offset: int = 0) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list jobs") from exc
        return [job_from_row(row) for row in rows]

    def count(self, *, status: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS total FROM jobs"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        try:
            row = self.conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count jobs") from exc
        return int(row["total"])

    def add_event(self, event: JobEvent) -> int:
        created_at = event.created_at or utc_now()
        payload_json = json.dumps(event.payload) if event.payload is not None else None
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO job_events(job_id, level, message, payload_json, created_at)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (event.job_id, event.level, event.message, payload_json, created_at),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to add event for job {event.job_id}") from exc
        return int(cursor.lastrowid)

    def list_events(self, job_id: str, *, limit: int = 100) -> list[JobEvent]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM job_events
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list events for job {job_id}") from exc
        return [job_event_from_row(row) for row in reversed(rows)]

    def list_recent_events(self, *, limit: int = 100) -> list[JobEvent]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM job_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list recent job events") from exc
        return [job_event_from_row(row) for row in reversed(rows)]

    def close(self) -> None:
        self.conn.close()


def job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        id=str(row["id"]),
        type=row["type"],
        status=row["status"],
        input_user_id=str(row["input_user_id"]) if row["input_user_id"] else None,
        input_artwork_id=str(row["input_artwork_id"]) if row["input_artwork_id"] else None,
        artist_id=str(row["artist_id"]) if row["artist_id"] else None,
        total_files=int(row["total_files"]),
        completed_files=int(row["completed_files"]),
        skipped_files=int(row["skipped_files"]),
        failed_files=int(row["failed_files"]),
        cancel_requested=bool(row["cancel_requested"]),
        error_message=str(row["error_message"]) if row["error_message"] else None,
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] else None,
    )


def job_event_from_row(row: sqlite3.Row) -> JobEvent:
    payload_json = row["payload_json"]
    payload = json.loads(payload_json) if payload_json else None
    return JobEvent(
        id=int(row["id"]),
        job_id=str(row["job_id"]),
        level=row["level"],
        message=str(row["message"]),
        payload=payload,
        created_at=str(row["created_at"]),
    )
