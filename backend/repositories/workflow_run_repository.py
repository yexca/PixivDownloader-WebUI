from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


@dataclass(frozen=True)
class WorkflowNodeRun:
    id: int | None
    workflow_run_id: str
    node_id: str
    node_type: str
    title: str
    position: int
    status: str
    input: dict[str, object] = field(default_factory=dict)
    output: dict[str, object] = field(default_factory=dict)
    job_ids: list[str] = field(default_factory=list)
    error_message: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


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
    request: dict[str, object] = field(default_factory=dict)
    created_at: str | None = None
    finished_at: str | None = None
    node_runs: list[WorkflowNodeRun] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowRun:
    id: str
    status: str
    total: int
    completed: int
    failed: int
    skipped: int
    concurrency: int
    source: str = "manual"
    schedule_id: int | None = None
    created_at: str | None = None
    finished_at: str | None = None
    items: list[WorkflowRunItem] = field(default_factory=list)
    node_runs: list[WorkflowNodeRun] = field(default_factory=list)


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
                        concurrency, source, schedule_id, created_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.id,
                        run.status,
                        run.total,
                        run.completed,
                        run.failed,
                        run.skipped,
                        run.concurrency,
                        run.source,
                        run.schedule_id,
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
                        source = ?,
                        schedule_id = ?,
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
                        run.source,
                        run.schedule_id,
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
                        error_message, config_json, request_json, created_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.run_id,
                        item.draft_id,
                        item.title,
                        item.status,
                        json.dumps(item.job_ids),
                        item.error_message,
                        json.dumps(item.config),
                        json.dumps(item.request) if item.request else None,
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
                        request_json = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        item.status,
                        json.dumps(item.job_ids),
                        item.error_message,
                        json.dumps(item.config),
                        json.dumps(item.request) if item.request else None,
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
        return workflow_run_from_row(row, self.list_items(run_id), self.list_node_runs(run_id))

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
        return [
            workflow_run_from_row(
                row,
                self.list_items(str(row["id"])),
                self.list_node_runs(str(row["id"])),
            )
            for row in rows
        ]

    def list_runs_by_status(self, status: str) -> list[WorkflowRun]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_runs
                WHERE status = ?
                ORDER BY created_at
                """,
                (status,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow runs with status {status}") from exc
        return [
            workflow_run_from_row(
                row,
                self.list_items(str(row["id"])),
                self.list_node_runs(str(row["id"])),
            )
            for row in rows
        ]

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

    def create_node_run(self, node_run: WorkflowNodeRun) -> int:
        created_at = node_run.created_at or utc_now()
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO workflow_node_runs(
                        workflow_run_id, node_id, node_type, title, position,
                        status, input_json, output_json, job_ids_json,
                        error_message, created_at, started_at, finished_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_run.workflow_run_id,
                        node_run.node_id,
                        node_run.node_type,
                        node_run.title,
                        node_run.position,
                        node_run.status,
                        json.dumps(node_run.input),
                        json.dumps(node_run.output),
                        json.dumps(node_run.job_ids),
                        node_run.error_message,
                        created_at,
                        node_run.started_at,
                        node_run.finished_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"failed to create workflow node run for {node_run.workflow_run_id}"
            ) from exc
        return int(cursor.lastrowid)

    def update_node_run(self, node_run: WorkflowNodeRun) -> None:
        if node_run.id is None:
            raise ValueError("workflow node run id is required")
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE workflow_node_runs
                    SET status = ?,
                        input_json = ?,
                        output_json = ?,
                        job_ids_json = ?,
                        error_message = ?,
                        started_at = ?,
                        finished_at = ?
                    WHERE id = ?
                    """,
                    (
                        node_run.status,
                        json.dumps(node_run.input),
                        json.dumps(node_run.output),
                        json.dumps(node_run.job_ids),
                        node_run.error_message,
                        node_run.started_at,
                        node_run.finished_at,
                        node_run.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update workflow node run {node_run.id}") from exc

    def list_node_runs(self, run_id: str) -> list[WorkflowNodeRun]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_node_runs
                WHERE workflow_run_id = ?
                ORDER BY position, id
                """,
                (run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to list workflow node runs for {run_id}") from exc
        return self._hydrate_node_job_ids([workflow_node_run_from_row(row) for row in rows])

    def last_item_status(self, draft_id: str, *, exclude_run_id: str | None = None) -> str | None:
        params: list[object] = [draft_id]
        excluded = ""
        if exclude_run_id is not None:
            excluded = "AND run_id != ?"
            params.append(exclude_run_id)
        try:
            row = self.conn.execute(
                f"""
                SELECT status FROM workflow_run_items
                WHERE draft_id = ?
                  {excluded}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch last workflow item for {draft_id}") from exc
        return str(row["status"]) if row is not None else None

    def close(self) -> None:
        self.conn.close()

    def _hydrate_node_job_ids(self, node_runs: list[WorkflowNodeRun]) -> list[WorkflowNodeRun]:
        node_ids = [node.id for node in node_runs if node.id is not None]
        if not node_ids:
            return node_runs
        placeholders = ", ".join("?" for _ in node_ids)
        try:
            rows = self.conn.execute(
                f"""
                SELECT workflow_node_run_id, id
                FROM jobs
                WHERE workflow_node_run_id IN ({placeholders})
                ORDER BY created_at, id
                """,
                node_ids,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to hydrate workflow node job links") from exc
        job_ids_by_node: dict[int, list[str]] = {}
        for row in rows:
            node_id = int(row["workflow_node_run_id"])
            job_ids_by_node.setdefault(node_id, []).append(str(row["id"]))
        return [
            replace(
                node,
                job_ids=dedupe([*node.job_ids, *job_ids_by_node.get(node.id or 0, [])]),
            )
            for node in node_runs
        ]


def workflow_run_from_row(
    row: sqlite3.Row,
    items: list[WorkflowRunItem],
    node_runs: list[WorkflowNodeRun],
) -> WorkflowRun:
    source = "manual"
    schedule_id = None
    with suppress(IndexError):
        source = str(row["source"] or "manual")
        schedule_id = int(row["schedule_id"]) if row["schedule_id"] is not None else None
    return WorkflowRun(
        id=str(row["id"]),
        status=str(row["status"]),
        total=int(row["total"]),
        completed=int(row["completed"]),
        failed=int(row["failed"]),
        skipped=int(row["skipped"]),
        concurrency=int(row["concurrency"]),
        source=source,
        schedule_id=schedule_id,
        created_at=row["created_at"],
        finished_at=row["finished_at"],
        items=items,
        node_runs=node_runs,
    )


def workflow_node_run_from_row(row: sqlite3.Row) -> WorkflowNodeRun:
    return WorkflowNodeRun(
        id=int(row["id"]),
        workflow_run_id=str(row["workflow_run_id"]),
        node_id=str(row["node_id"]),
        node_type=str(row["node_type"]),
        title=str(row["title"]),
        position=int(row["position"]),
        status=str(row["status"]),
        input=parse_json_dict(row["input_json"]),
        output=parse_json_dict(row["output_json"]),
        job_ids=parse_json_list(row["job_ids_json"]),
        error_message=row["error_message"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def workflow_run_item_from_row(row: sqlite3.Row) -> WorkflowRunItem:
    request_json = None
    with suppress(IndexError):
        request_json = row["request_json"]
    return WorkflowRunItem(
        id=int(row["id"]),
        run_id=str(row["run_id"]),
        draft_id=str(row["draft_id"]),
        title=str(row["title"]),
        status=str(row["status"]),
        job_ids=parse_json_list(row["job_ids_json"]),
        error_message=row["error_message"],
        config=parse_json_dict(row["config_json"]),
        request=parse_json_dict(request_json),
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


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
