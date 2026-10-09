from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime

from backend.domain.entities import WorkflowTriggerRuntime
from backend.services.workflow_trigger_compiler import workflow_trigger_definition
from backend.services.workflow_trigger_facade_service import config_from_meta

logger = logging.getLogger(__name__)


def parsed_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def repair_legacy_workflows(conn: sqlite3.Connection) -> None:
    # Only generated, unedited definitions are safe to reconstruct automatically.
    # The original table was removed in 019. Edits after 017 have a later timestamp.
    rows = conn.execute("""
        SELECT d.id, d.definition_json, d.updated_at, m.applied_at FROM workflow_definitions d
        JOIN schema_migrations m ON m.version = '017'
        WHERE d.id LIKE 'scheduled-task:%'
    """).fetchall()
    for row in rows:
        if parsed_timestamp(row["updated_at"]) > parsed_timestamp(row["applied_at"]):
            logger.warning(
                "Legacy workflow %s was edited after 017; review its action semantics manually",
                row["id"],
            )
            continue
        original = json.loads(row["definition_json"])
        meta = original.get("metadata", {}).get("compat_scheduled_task")
        if not isinstance(meta, dict):
            continue
        task = WorkflowTriggerRuntime(
            id=None,
            name=original.get("name", ""),
            action=meta["action"],
            status="paused",
            target_artist_id=meta.get("target_artist_id", ""),
            interval_days=meta.get("interval_days", 1),
        )
        repaired = workflow_trigger_definition(task, config_from_meta(meta)).model_dump(mode="json")
        repaired["metadata"] = original.get("metadata", {})
        conn.execute(
            "UPDATE workflow_definitions SET definition_json = ? WHERE id = ?",
            (json.dumps(repaired), row["id"]),
        )
