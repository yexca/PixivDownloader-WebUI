CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    target_artist_id TEXT NOT NULL,
    interval_days INTEGER NOT NULL,
    run_after_startup INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_success_at TEXT,
    next_run_at TEXT,
    last_job_id TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status_next_run
    ON scheduled_tasks(status, next_run_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_artist
    ON scheduled_tasks(target_artist_id);
