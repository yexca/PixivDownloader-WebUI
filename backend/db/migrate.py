from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.core.config import SettingsService
from backend.core.errors import ConfigError, DatabaseError
from backend.core.paths import database_path as default_database_path
from backend.core.paths import settings_path as default_settings_path
from backend.db.connection import connect

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path


def migrate_database(
    db_path: Path | str | None = None,
    *,
    settings_json_path: Path | str | None = None,
) -> list[Migration]:
    path = Path(db_path) if db_path is not None else default_database_path()
    settings_path = (
        Path(settings_json_path) if settings_json_path is not None else default_settings_path()
    )

    with connect(path) as conn:
        ensure_migration_table(conn)
        applied_versions = get_applied_versions(conn)
        applied_migrations: list[Migration] = []

        for migration in discover_migrations():
            if migration.version in applied_versions:
                continue
            apply_migration(conn, migration)
            applied_migrations.append(migration)

        sync_settings_from_json(conn, settings_path)

    return applied_migrations


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    except sqlite3.Error as exc:
        raise DatabaseError("failed to create schema_migrations table") from exc


def get_applied_versions(conn: sqlite3.Connection) -> set[str]:
    try:
        cursor = conn.execute("SELECT version FROM schema_migrations")
        return {str(row["version"]) for row in cursor.fetchall()}
    except sqlite3.Error as exc:
        raise DatabaseError("failed to read applied migrations") from exc


def discover_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version, _, name = path.stem.partition("_")
        if not version or not name:
            raise DatabaseError(f"invalid migration file name: {path.name}")
        migrations.append(Migration(version=version, name=name, path=path))
    return migrations


def apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    try:
        conn.execute("BEGIN")
        conn.executescript(sql)
        conn.execute(
            """
            INSERT INTO schema_migrations(version, name, applied_at)
            VALUES(?, ?, ?)
            """,
            (migration.version, migration.name, utc_now()),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(f"failed to apply migration {migration.path.name}") from exc


def sync_settings_from_json(conn: sqlite3.Connection, settings_path: Path) -> None:
    if not settings_path.exists():
        logger.info("settings file not found; skipping settings table sync")
        return

    try:
        settings = SettingsService(settings_path).load()
    except ConfigError as exc:
        raise DatabaseError("failed to migrate settings from JSON") from exc

    values = settings.to_dict()
    try:
        with conn:
            for key, value in values.items():
                conn.execute(
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
        raise DatabaseError("failed to sync settings table") from exc


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> None:
    applied = migrate_database()
    if applied:
        names = ", ".join(f"{migration.version}_{migration.name}" for migration in applied)
        print(f"Applied migrations: {names}")
    else:
        print("Database is up to date.")


if __name__ == "__main__":
    main()
