ALTER TABLE jobs
    ADD COLUMN workflow_node_run_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_jobs_workflow_node_run_id
    ON jobs(workflow_node_run_id);

UPDATE jobs
SET workflow_node_run_id = (
    SELECT workflow_node_runs.id
    FROM workflow_node_runs, json_each(workflow_node_runs.job_ids_json)
    WHERE json_each.value = jobs.id
    ORDER BY workflow_node_runs.id DESC
    LIMIT 1
)
WHERE workflow_node_run_id IS NULL
  AND EXISTS (
      SELECT 1
      FROM workflow_node_runs, json_each(workflow_node_runs.job_ids_json)
      WHERE json_each.value = jobs.id
  );
