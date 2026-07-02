from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    name: str
    definition: dict[str, object]
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class WorkflowTrigger:
    id: int | None
    workflow_definition_id: str
    status: str
    schedule: dict[str, object]
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class WorkflowDefinitionWithTriggers:
    definition: WorkflowDefinition
    triggers: list[WorkflowTrigger] = field(default_factory=list)


class WorkflowDefinitionRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def upsert_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        now = utc_now()
        created_at = definition.created_at or now
        updated_at = now
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO workflow_definitions(
                        id, name, definition_json, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        definition_json = excluded.definition_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        definition.id,
                        definition.name,
                        json.dumps(definition.definition, ensure_ascii=False),
                        created_at,
                        updated_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to save workflow definition {definition.id}") from exc
        saved = self.get_definition(definition.id)
        if saved is None:
            raise DatabaseError(f"failed to reload workflow definition {definition.id}")
        return saved

    def get_definition(self, definition_id: str) -> WorkflowDefinition | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM workflow_definitions WHERE id = ?",
                (definition_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch workflow definition {definition_id}") from exc
        return workflow_definition_from_row(row) if row is not None else None

    def delete_definition(self, definition_id: str) -> bool:
        try:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM workflow_triggers WHERE workflow_definition_id = ?",
                    (definition_id,),
                )
                cursor = self.conn.execute(
                    "DELETE FROM workflow_definitions WHERE id = ?",
                    (definition_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to delete workflow definition {definition_id}") from exc
        return cursor.rowcount > 0

    def list_definitions(self) -> list[WorkflowDefinitionWithTriggers]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_definitions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list workflow definitions") from exc
        return [
            WorkflowDefinitionWithTriggers(
                definition=workflow_definition_from_row(row),
                triggers=self.list_triggers(str(row["id"])),
            )
            for row in rows
        ]

    def create_trigger(self, trigger: WorkflowTrigger) -> WorkflowTrigger:
        now = utc_now()
        try:
            with self.conn:
                cursor = self.conn.execute(
                    """
                    INSERT INTO workflow_triggers(
                        workflow_definition_id, status, schedule_json, next_run_at,
                        last_run_at, last_success_at, last_error_code,
                        last_error_message, created_at, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trigger.workflow_definition_id,
                        trigger.status,
                        json.dumps(trigger.schedule, ensure_ascii=False),
                        trigger.next_run_at,
                        trigger.last_run_at,
                        trigger.last_success_at,
                        trigger.last_error_code,
                        trigger.last_error_message,
                        trigger.created_at or now,
                        trigger.updated_at or now,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError("failed to create workflow trigger") from exc
        created = self.get_trigger(int(cursor.lastrowid))
        if created is None:
            raise DatabaseError("failed to reload workflow trigger")
        return created

    def update_trigger(self, trigger: WorkflowTrigger) -> None:
        if trigger.id is None:
            raise ValueError("workflow trigger id is required")
        try:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE workflow_triggers
                    SET workflow_definition_id = ?,
                        status = ?,
                        schedule_json = ?,
                        next_run_at = ?,
                        last_run_at = ?,
                        last_success_at = ?,
                        last_error_code = ?,
                        last_error_message = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        trigger.workflow_definition_id,
                        trigger.status,
                        json.dumps(trigger.schedule, ensure_ascii=False),
                        trigger.next_run_at,
                        trigger.last_run_at,
                        trigger.last_success_at,
                        trigger.last_error_code,
                        trigger.last_error_message,
                        utc_now(),
                        trigger.id,
                    ),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to update workflow trigger {trigger.id}") from exc

    def get_trigger(self, trigger_id: int) -> WorkflowTrigger | None:
        try:
            row = self.conn.execute(
                "SELECT * FROM workflow_triggers WHERE id = ?",
                (trigger_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch workflow trigger {trigger_id}") from exc
        return workflow_trigger_from_row(row) if row is not None else None

    def delete_trigger(self, trigger_id: int) -> bool:
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "DELETE FROM workflow_triggers WHERE id = ?",
                    (trigger_id,),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to delete workflow trigger {trigger_id}") from exc
        return cursor.rowcount > 0

    def list_triggers(self, definition_id: str | None = None) -> list[WorkflowTrigger]:
        params: tuple[object, ...] = ()
        where = ""
        if definition_id is not None:
            where = "WHERE workflow_definition_id = ?"
            params = (definition_id,)
        try:
            rows = self.conn.execute(
                f"""
                SELECT * FROM workflow_triggers
                {where}
                ORDER BY updated_at DESC
                """,
                params,
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list workflow triggers") from exc
        return [workflow_trigger_from_row(row) for row in rows]

    def due_triggers(self, now: str) -> list[WorkflowTrigger]:
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM workflow_triggers
                WHERE status = 'active'
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at, id
                """,
                (now,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list due workflow triggers") from exc
        return [workflow_trigger_from_row(row) for row in rows]

    def close(self) -> None:
        self.conn.close()


def workflow_definition_from_row(row: sqlite3.Row) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=str(row["id"]),
        name=str(row["name"]),
        definition=parse_json_dict(row["definition_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def workflow_trigger_from_row(row: sqlite3.Row) -> WorkflowTrigger:
    return WorkflowTrigger(
        id=int(row["id"]),
        workflow_definition_id=str(row["workflow_definition_id"]),
        status=str(row["status"]),
        schedule=parse_json_dict(row["schedule_json"]),
        next_run_at=row["next_run_at"],
        last_run_at=row["last_run_at"],
        last_success_at=row["last_success_at"],
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def parse_json_dict(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
