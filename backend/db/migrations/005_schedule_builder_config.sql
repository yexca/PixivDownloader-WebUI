ALTER TABLE scheduled_tasks
    ADD COLUMN config_json TEXT;

ALTER TABLE scheduled_tasks
    ADD COLUMN last_run_summary_json TEXT;
