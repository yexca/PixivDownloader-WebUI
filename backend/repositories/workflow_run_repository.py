from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


@dataclass(frozen=True)
class WorkflowRunItem:
    id: int | None
    run_id: str
    draft_id: str
    title: str
    status: str
    job_ids: list[str] = field(default_factory=list)
    error_message: str | None = None
    config: dict[str, object] = field(default_factory=dict)
    created_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class WorkflowRun:
    id: str
    status: str
    total: int
    completed: int
    failed: int
    skipped: int
    concurrency: int
    created_at: str | None = None
    finished_at: str | None = None
    items: list[WorkflowRunItem] = field(default_factory=list)


class WorkflowRunRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def create_run(self, run: WorkflowRun) -> None:
        created_at = run.created_at or utc_now()
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO workflow_runs(
                        id, status, total, completed, failed, skipped,
                        concurrency, created_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.id,
                        run.status,
                        run.total,
                        run.completed,
                        run.failed,
                        run.skipped,
                        run.concurrency,
                        created_at,
                        run.finished_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to create workflow run {run.id}") from exc

    def update_run(self, run: WorkflowRun) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE workflow_runs
                    SET status = ?,
                        total = ?,
                        completed = ?,
                        failed = ?,
                        skipped = ?,
                        concurrency = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        run.status,
                        run.total,
                        run.completed,
                        run.failed,
                        run.skipped,
                        run.concurrency,
                        run.finished_at,
                        run.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update workflow run {run.id}") from exc

    def create_item(self, item: WorkflowRunItem) -> int:
        created_at = item.created_at or utc_now()
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO workflow_run_items(
                        run_id, draft_id, title, status, job_ids_json,
                        error_message, config_json, created_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.run_id,
                        item.draft_id,
                        item.title,
                        item.status,
                        json.dumps(item.job_ids),
                        item.error_message,
                        json.dumps(item.config),
                        created_at,
                        item.finished_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to create workflow run item for {item.run_id}") from exc
        return int(cursor.lastrowid)

    def update_item(self, item: WorkflowRunItem) -> None:
        if item.id is None:
            raise ValueError("workflow run item id is required")
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE workflow_run_items
                    SET status = ?,
                        job_ids_json = ?,
                        error_message = ?,
                        config_json = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        item.status,
                        json.dumps(item.job_ids),
                        item.error_message,
                        json.dumps(item.config),
                        item.finished_at,
                        item.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update workflow run item {item.id}") from exc

    def get_run(self, run_id: str) -> WorkflowRun | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM workflow_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch workflow run {run_id}") from exc
        if row is None:
            return None
        return workflow_run_from_row(row, self.list_items(run_id))

    def list_runs(self, *, limit: int = 5, offset: int = 0) -> list[WorkflowRun]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_runs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list workflow runs") from exc
        return [workflow_run_from_row(row, self.list_items(str(row["id"]))) for row in rows]

    def count_runs(self) -> int:
        try:
            row = self.conn.execute("SELECT COUNT(*) AS total FROM workflow_runs").fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to count workflow runs") from exc
        return int(row["total"])

    def list_items(self, run_id: str) -> list[WorkflowRunItem]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_run_items
                WHERE run_id = ?
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow run items for {run_id}") from exc
        return [workflow_run_item_from_row(row) for row in rows]

    def last_item_status(self, draft_id: str) -> str | None:
        try:
            row = self.conn.execute(
                """
                SELECT status FROM workflow_run_items
                WHERE draft_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (draft_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch last workflow item for {draft_id}") from exc
        return str(row["status"]) if row is not None else None

    def close(self) -> None:
        self.conn.close()


def workflow_run_from_row(row: sqlite3.Row, items: list[WorkflowRunItem]) -> WorkflowRun:
    return WorkflowRun(
        id=str(row["id"]),
        status=str(row["status"]),
        total=int(row["total"]),
        completed=int(row["completed"]),
        failed=int(row["failed"]),
        skipped=int(row["skipped"]),
        concurrency=int(row["concurrency"]),
        created_at=row["created_at"],
        finished_at=row["finished_at"],
        items=items,
    )


def workflow_run_item_from_row(row: sqlite3.Row) -> WorkflowRunItem:
    return WorkflowRunItem(
        id=int(row["id"]),
        run_id=str(row["run_id"]),
        draft_id=str(row["draft_id"]),
        title=str(row["title"]),
        status=str(row["status"]),
        job_ids=parse_json_list(row["job_ids_json"]),
        error_message=row["error_message"],
        config=parse_json_dict(row["config_json"]),
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


def parse_json_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def parse_json_dict(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
