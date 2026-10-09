CREATE TABLE workflow_execution_claims (
    workflow_run_id TEXT PRIMARY KEY REFERENCES workflow_runs(id) ON DELETE CASCADE,
    owner TEXT NOT NULL
);
CREATE TABLE workflow_scheduler_claim (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    owner TEXT NOT NULL
);
