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
                        options_json,
                        workflow_run_id,
                        workflow_item_id,
                        workflow_node_run_id,
                        workflow_source,
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
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.type,
                        job.status,
                        job.input_user_id,
                        job.input_artwork_id,
                        json.dumps(job.options) if job.options else None,
                        job.workflow_run_id,
                        job.workflow_item_id,
                        job.workflow_node_run_id,
                        job.workflow_source,
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
                        workflow_run_id = ?,
                        workflow_item_id = ?,
                        workflow_node_run_id = ?,
                        workflow_source = ?,
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
                        job.workflow_run_id,
                        job.workflow_item_id,
                        job.workflow_node_run_id,
                        job.workflow_source,
                        job.started_at,
                        job.finished_at,
                        job.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update job {job.id}") from exc

    def update_options(self, job_id: str, options: dict[str, object]) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE jobs SET options_json = ? WHERE id = ?",
                    (json.dumps(options) if options else None, job_id),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update job {job_id} options") from exc

    def update_workflow_link(
        self,
        job_id: str,
        *,
        workflow_run_id: str,
        workflow_item_id: int,
        workflow_source: str,
        workflow_node_run_id: int | None = None,
    ) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE jobs
                    SET workflow_run_id = ?,
                        workflow_item_id = ?,
                        workflow_node_run_id = ?,
                        workflow_source = ?
                    WHERE id = ?
                    """,
                    (
                        workflow_run_id,
                        workflow_item_id,
                        workflow_node_run_id,
                        workflow_source,
                        job_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update workflow link for job {job_id}") from exc

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

    def list_by_ids(self, job_ids: list[str]) -> list[Job]:
        if not job_ids:
            return []
        placeholders = ",".join("?" for _ in job_ids)
        try:
            rows = self.conn.execute(
                f"SELECT * FROM jobs WHERE id IN ({placeholders})",
                job_ids,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to fetch jobs by id") from exc
        jobs_by_id = {str(row["id"]): job_from_row(row) for row in rows}
        return [jobs_by_id[job_id] for job_id in job_ids if job_id in jobs_by_id]

    def list_child_jobs(self, job_id: str, *, limit: int = 20) -> list[Job]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE json_extract(options_json, '$.source_job_id') = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list child jobs for {job_id}") from exc
        return [job_from_row(row) for row in rows]

    def list_by_workflow_node_run_id(self, node_run_id: int) -> list[Job]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE workflow_node_run_id = ?
                ORDER BY created_at, id
                """,
                (node_run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list jobs for workflow node run {node_run_id}") from exc
        return [job_from_row(row) for row in rows]

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

    def count_active_one_time(self) -> int:
        try:
            row = self.conn.execute(
                """
                SELECT COUNT(*) AS count FROM jobs
                WHERE status IN ('queued', 'running')
                  AND json_extract(options_json, '$.activation_scope') = 'one_time'
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count active one-time jobs") from exc
        return int(row["count"] if row is not None else 0)

    def list_inactive_one_time(self, *, limit: int) -> list[Job]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'inactive'
                  AND json_extract(options_json, '$.activation_scope') = 'one_time'
                ORDER BY created_at
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list inactive one-time jobs") from exc
        return [job_from_row(row) for row in rows]

    def list_active_orphan_jobs(self) -> list[Job]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('inactive', 'queued', 'running')
                  AND workflow_run_id IS NULL
                  AND workflow_item_id IS NULL
                ORDER BY created_at
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list active orphan jobs") from exc
        return [job_from_row(row) for row in rows]

    def requeue_jobs(self, job_ids: list[str]) -> list[Job]:
        if not job_ids:
            return []
        try:
            with self.conn:
                for job_id in job_ids:
                    self.conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'queued',
                            total_files = 0,
                            completed_files = 0,
                            skipped_files = 0,
                            failed_files = 0,
                            error_message = NULL,
                            started_at = NULL,
                            finished_at = NULL
                        WHERE id = ?
                          AND status = 'running'
                        """,
                        (job_id,),
                    )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to requeue jobs") from exc
        return self.list_by_ids(job_ids)

    def requeue_running(self) -> list[Job]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'running'
                ORDER BY created_at
                """
            ).fetchall()
            jobs = [job_from_row(row) for row in rows]
            with self.conn:
                for job in jobs:
                    self.conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'queued',
                            total_files = 0,
                            completed_files = 0,
                            skipped_files = 0,
                            failed_files = 0,
                            error_message = NULL,
                            started_at = NULL,
                            finished_at = NULL
                        WHERE id = ?
                        """,
                        (job.id,),
                    )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to requeue running jobs") from exc
        return [self.get_by_id(job.id) or job for job in jobs]

    def find_active(
        self,
        *,
        job_type: str,
        user_id: str | None = None,
        artwork_id: str | None = None,
    ) -> Job | None:
        try:
            row = self.conn.execute(
                """
                SELECT * FROM jobs
                WHERE type = ?
                  AND status IN ('inactive', 'queued', 'running')
                  AND (
                    (? IS NULL AND input_user_id IS NULL)
                    OR input_user_id = ?
                  )
                  AND (
                    (? IS NULL AND input_artwork_id IS NULL)
                    OR input_artwork_id = ?
                  )
                ORDER BY created_at
                LIMIT 1
                """,
                (job_type, user_id, user_id, artwork_id, artwork_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to find active job") from exc
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

    def list_recent_events(
        self,
        *,
        level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobEvent]:
        sql = "SELECT * FROM job_events"
        params: list[object] = []
        if level:
            sql += " WHERE level = ?"
            params.append(level)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list recent job events") from exc
        return [job_event_from_row(row) for row in reversed(rows)]

    def count_events(self, *, level: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS total FROM job_events"
        params: list[object] = []
        if level:
            sql += " WHERE level = ?"
            params.append(level)
        try:
            row = self.conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count job events") from exc
        return int(row["total"])

    def close(self) -> None:
        self.conn.close()


def job_from_row(row: sqlite3.Row) -> Job:
    try:
        options_json = row["options_json"]
    except IndexError:
        options_json = None
    options = json.loads(options_json) if options_json else {}
    return Job(
        id=str(row["id"]),
        type=row["type"],
        status=row["status"],
        input_user_id=str(row["input_user_id"]) if row["input_user_id"] else None,
        input_artwork_id=str(row["input_artwork_id"]) if row["input_artwork_id"] else None,
        options=options,
        workflow_run_id=optional_row_str(row, "workflow_run_id"),
        workflow_item_id=optional_row_int(row, "workflow_item_id"),
        workflow_node_run_id=optional_row_int(row, "workflow_node_run_id"),
        workflow_source=optional_row_str(row, "workflow_source"),
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


def optional_row_str(row: sqlite3.Row, key: str) -> str | None:
    try:
        value = row[key]
    except IndexError:
        return None
    return str(value) if value else None


def optional_row_int(row: sqlite3.Row, key: str) -> int | None:
    try:
        value = row[key]
    except IndexError:
        return None
    return int(value) if value is not None else None


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
