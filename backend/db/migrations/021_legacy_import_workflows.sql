CREATE TABLE IF NOT EXISTS legacy_imports (
    id TEXT PRIMARY KEY,
    workflow_run_id TEXT,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL,
    total_rows INTEGER NOT NULL DEFAULT 0,
    imported_artists INTEGER NOT NULL DEFAULT 0,
    skipped_rows INTEGER NOT NULL DEFAULT 0,
    last_cursor TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS legacy_import_artists (
    import_id TEXT NOT NULL,
    artist_id TEXT NOT NULL,
    legacy_latest_download_id TEXT,
    hydration_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (import_id, artist_id),
    FOREIGN KEY (import_id) REFERENCES legacy_imports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_legacy_imports_workflow_run_id
    ON legacy_imports(workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_legacy_import_artists_import_id
    ON legacy_import_artists(import_id);
