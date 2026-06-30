UPDATE jobs
SET options_json = json_set(
    json_remove(
        json_remove(
            json_remove(COALESCE(options_json, '{}'), '$.workflow_run_id'),
            '$.workflow_item_id'
        ),
        '$.workflow_source'
    ),
    '$.activation_scope',
    COALESCE(json_extract(options_json, '$.activation_scope'), 'one_time')
)
WHERE options_json IS NOT NULL
  AND (
    json_extract(options_json, '$.workflow_run_id') IS NOT NULL
    OR json_extract(options_json, '$.workflow_item_id') IS NOT NULL
    OR json_extract(options_json, '$.workflow_source') IS NOT NULL
  );
