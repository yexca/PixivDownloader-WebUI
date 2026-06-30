CREATE TABLE IF NOT EXISTS workflow_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_definition_id TEXT NOT NULL,
    status TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    next_run_at TEXT,
    last_run_at TEXT,
    last_success_at TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workflow_definition_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_triggers_status_next_run
    ON workflow_triggers(status, next_run_at);

CREATE INDEX IF NOT EXISTS idx_workflow_triggers_definition_id
    ON workflow_triggers(workflow_definition_id);
