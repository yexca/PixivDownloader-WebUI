ALTER TABLE jobs
    ADD COLUMN workflow_run_id TEXT;

ALTER TABLE jobs
    ADD COLUMN workflow_item_id INTEGER;

ALTER TABLE jobs
    ADD COLUMN workflow_source TEXT;

CREATE INDEX IF NOT EXISTS idx_jobs_workflow_run_id
    ON jobs(workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_jobs_workflow_item_id
    ON jobs(workflow_item_id);
