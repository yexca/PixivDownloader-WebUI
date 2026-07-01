ALTER TABLE workflow_runs
    ADD COLUMN name TEXT NOT NULL DEFAULT 'Workflow run';

ALTER TABLE workflow_runs
    ADD COLUMN definition_id TEXT;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_definition_id
    ON workflow_runs(definition_id);
