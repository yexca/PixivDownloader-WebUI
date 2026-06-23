from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.core.errors import DatabaseError
from backend.db.connection import connect
from backend.repositories._time import utc_now


class SettingsRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = connect(db_path)

    def set(self, key: str, value: Any) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO settings(key, value_json, updated_at)
                    VALUES(?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value), utc_now()),
                )
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to save setting {key}") from exc

    def get(self, key: str, default: Any = None) -> Any:
        try:
            row = self.conn.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise DatabaseError(f"failed to fetch setting {key}") from exc
        if row is None:
            return default
        return json.loads(row["value_json"])

    def all(self) -> dict[str, Any]:
        try:
            rows = self.conn.execute("SELECT key, value_json FROM settings ORDER BY key").fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError("failed to list settings") from exc
        return {str(row["key"]): json.loads(row["value_json"]) for row in rows}

    def close(self) -> None:
        self.conn.close()
