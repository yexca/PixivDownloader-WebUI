ALTER TABLE workflow_runs
    ADD COLUMN source TEXT NOT NULL DEFAULT 'manual';

ALTER TABLE workflow_runs
    ADD COLUMN schedule_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_schedule_id
    ON workflow_runs(schedule_id);
