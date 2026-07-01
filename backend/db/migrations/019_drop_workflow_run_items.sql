DROP TABLE IF EXISTS workflow_run_items;

DROP INDEX IF EXISTS idx_jobs_workflow_item_id;

ALTER TABLE jobs
    DROP COLUMN workflow_item_id;

DROP TABLE IF EXISTS scheduled_tasks;
