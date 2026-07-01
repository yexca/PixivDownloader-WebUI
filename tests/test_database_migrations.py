import sqlite3

from backend.db.migrate import migrate_database


def table_names(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def test_fresh_database_migration_creates_webui_schema(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"

    applied = migrate_database(db_path, settings_json_path=tmp_path / "ignored.json")

    assert [migration.version for migration in applied] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
        "007",
        "008",
        "009",
        "010",
        "011",
        "012",
        "013",
        "014",
        "015",
        "016",
        "017",
    ]
    assert {
        "schema_migrations",
        "artists",
        "artworks",
        "artwork_files",
        "jobs",
        "job_events",
        "settings",
        "local_tags",
        "artist_local_tags",
        "scheduled_tasks",
        "workflow_runs",
        "workflow_run_items",
        "workflow_node_runs",
        "workflow_candidate_sets",
        "workflow_candidate_artworks",
        "workflow_definitions",
        "workflow_triggers",
        "artist_name_history",
    }.issubset(table_names(db_path))
    assert "pic" not in table_names(db_path)


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "pixiv.sqlite3"

    first_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")
    second_applied = migrate_database(db_path, settings_json_path=tmp_path / "missing.json")

    conn = sqlite3.connect(db_path)
    try:
        migration_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    finally:
        conn.close()

    assert len(first_applied) == 17
    assert second_applied == []
    assert migration_count == 17
