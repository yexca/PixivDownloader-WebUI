from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.core.errors import DatabaseError
from backend.core.paths import database_path as default_database_path


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else default_database_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"failed to connect to database: {path}") from exc
