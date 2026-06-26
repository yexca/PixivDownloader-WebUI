from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.domain.entities import ScheduledTask
from backend.repositories._time import utc_now


class ScheduledTaskRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def create(self, task: ScheduledTask) -> ScheduledTask:
        now = utc_now()
        created = replace(task, created_at=task.created_at or now, updated_at=now)
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO scheduled_tasks(
                        name,
                        action,
                        status,
                        target_artist_id,
                        interval_days,
                        run_after_startup,
                        last_run_at,
                        last_success_at,
                        next_run_at,
                        last_job_id,
                        last_error_code,
                        last_error_message,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    scheduled_task_values(created, include_id=False),
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to create scheduled task") from exc
        return self.get_by_id(int(cursor.lastrowid)) or created

    def update(self, task: ScheduledTask) -> None:
        if task.id is None:
            raise DatabaseError("scheduled task id is required for update")
        updated = replace(task, updated_at=utc_now())
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET name = ?,
                        action = ?,
                        status = ?,
                        target_artist_id = ?,
                        interval_days = ?,
                        run_after_startup = ?,
                        last_run_at = ?,
                        last_success_at = ?,
                        next_run_at = ?,
                        last_job_id = ?,
                        last_error_code = ?,
                        last_error_message = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    scheduled_task_values(updated, include_id=True, include_created_at=False),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update scheduled task {task.id}") from exc

    def get_by_id(self, task_id: int) -> ScheduledTask | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch scheduled task {task_id}") from exc
        return scheduled_task_from_row(row) if row is not None else None

    def list(self) -> list[ScheduledTask]:
        try:
            rows = self.conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY updated_at DESC"
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list scheduled tasks") from exc
        return [scheduled_task_from_row(row) for row in rows]

    def due(self, now: str) -> list[ScheduledTask]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM scheduled_tasks
                WHERE status = 'active'
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at, id
                """,
                (now,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list due scheduled tasks") from exc
        return [scheduled_task_from_row(row) for row in rows]

    def delete(self, task_id: int) -> bool:
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "DELETE FROM scheduled_tasks WHERE id = ?",
                    (task_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to delete scheduled task {task_id}") from exc
        return cursor.rowcount > 0

    def close(self) -> None:
        self.conn.close()


def scheduled_task_values(
    task: ScheduledTask,
    *,
    include_id: bool,
    include_created_at: bool = True,
) -> tuple[object, ...]:
    values: list[object] = [
        task.name,
        task.action,
        task.status,
        task.target_artist_id,
        task.interval_days,
        int(task.run_after_startup),
        task.last_run_at,
        task.last_success_at,
        task.next_run_at,
        task.last_job_id,
        task.last_error_code,
        task.last_error_message,
    ]
    if include_created_at:
        values.append(task.created_at)
    values.append(task.updated_at)
    if include_id:
        values.append(task.id)
    return tuple(values)


def scheduled_task_from_row(row: sqlite3.Row) -> ScheduledTask:
    return ScheduledTask(
        id=int(row["id"]),
        name=str(row["name"]),
        action=row["action"],
        status=row["status"],
        target_artist_id=str(row["target_artist_id"]),
        interval_days=int(row["interval_days"]),
        run_after_startup=bool(row["run_after_startup"]),
        last_run_at=str(row["last_run_at"]) if row["last_run_at"] else None,
        last_success_at=str(row["last_success_at"]) if row["last_success_at"] else None,
        next_run_at=str(row["next_run_at"]) if row["next_run_at"] else None,
        last_job_id=str(row["last_job_id"]) if row["last_job_id"] else None,
        last_error_code=str(row["last_error_code"]) if row["last_error_code"] else None,
        last_error_message=str(row["last_error_message"]) if row["last_error_message"] else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
