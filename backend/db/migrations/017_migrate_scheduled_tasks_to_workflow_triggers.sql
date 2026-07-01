INSERT OR IGNORE INTO workflow_definitions(id, name, definition_json, created_at, updated_at)
SELECT
    'scheduled-task:' || CAST(id AS TEXT),
    name,
    json_object(
        'name', name,
        'metadata', json_object(
            'compat_scheduled_task', json_object(
                'action', action,
                'target_artist_id', target_artist_id,
                'interval_days', interval_days,
                'run_after_startup', CASE WHEN run_after_startup THEN json('true') ELSE json('false') END,
                'config', json(COALESCE(config_json, '{}'))
            )
        ),
        'nodes', json_array(
            json_object(
                'id', 'target',
                'type', 'artist_target',
                'title', 'Target artists',
                'config', json_object(
                    'scope', COALESCE(json_extract(config_json, '$.target.type'), 'single_artist'),
                    'artist_id', COALESCE(json_extract(config_json, '$.target.artist_id'), target_artist_id),
                    'artwork_id', json_extract(config_json, '$.target.artwork_id'),
                    'artist_ids', COALESCE(json_extract(config_json, '$.target.artist_ids'), json_array()),
                    'artwork_ids', COALESCE(json_extract(config_json, '$.target.artwork_ids'), json_array()),
                    'artist_source', COALESCE(json_extract(config_json, '$.target.artist_source'), 'artist_ids'),
                    'tag', json_extract(config_json, '$.target.tag'),
                    'tags', COALESCE(json_extract(config_json, '$.target.tags'), json_array()),
                    'days', json_extract(config_json, '$.target.days'),
                    'filters', COALESCE(json_extract(config_json, '$.filters'), json_array()),
                    'artist_selection', COALESCE(json_extract(config_json, '$.artist_selection'), 'oldest_checked_first'),
                    'skip_unavailable_artists', COALESCE(json_extract(config_json, '$.skip_unavailable_artists'), json('true')),
                    'max_artists', COALESCE(json_extract(config_json, '$.max_artists_per_run'), 25)
                )
            ),
            json_object(
                'id', 'sync',
                'type', 'sync_metadata',
                'title', 'Sync metadata',
                'config', json_object(
                    'mode',
                    CASE
                        WHEN json_extract(config_json, '$.download_options.full_download') THEN 'full'
                        ELSE 'incremental'
                    END
                )
            ),
            json_object(
                'id', 'collect',
                'type', 'collect_artworks',
                'title', 'Collect artworks',
                'config', json_object(
                    'mode',
                    CASE
                        WHEN json_extract(config_json, '$.download_options.full_download') THEN 'all_synced'
                        WHEN json_extract(config_json, '$.download_options.pending_only') THEN 'pending_files'
                        ELSE 'new_since_last_download'
                    END,
                    'max_artworks', json_extract(config_json, '$.download_options.max_artworks'),
                    'min_artwork_id', json_extract(config_json, '$.download_options.min_artwork_id'),
                    'max_artwork_id', json_extract(config_json, '$.download_options.max_artwork_id')
                )
            ),
            json_object(
                'id', 'filters',
                'type', 'filter_artworks',
                'title', 'Filter artworks',
                'config', json_object(
                    'stop_above_limit', json_extract(config_json, '$.download_options.stop_if_artwork_count_above')
                )
            ),
            json_object(
                'id', 'actions',
                'type', 'execute_actions',
                'title', 'Download files',
                'config', json_object(
                    'download', json('true'),
                    'execution_unit', 'artist',
                    'naming_rule', json_extract(config_json, '$.download_options.naming_rule')
                )
            )
        )
    ),
    created_at,
    updated_at
FROM scheduled_tasks
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_definitions
    WHERE workflow_definitions.id = 'scheduled-task:' || CAST(scheduled_tasks.id AS TEXT)
);

INSERT INTO workflow_triggers(
    workflow_definition_id,
    status,
    schedule_json,
    next_run_at,
    last_run_at,
    last_success_at,
    last_error_code,
    last_error_message,
    created_at,
    updated_at
)
SELECT
    'scheduled-task:' || CAST(id AS TEXT),
    status,
    json_object(
        'type', 'interval',
        'every', interval_days,
        'unit', 'days',
        'compat_scheduled_task', json_object(
            'action', action,
            'target_artist_id', target_artist_id,
            'interval_days', interval_days,
            'run_after_startup', CASE WHEN run_after_startup THEN json('true') ELSE json('false') END,
            'config', json(COALESCE(config_json, '{}'))
        )
    ),
    next_run_at,
    last_run_at,
    last_success_at,
    last_error_code,
    last_error_message,
    created_at,
    updated_at
FROM scheduled_tasks
WHERE NOT EXISTS (
    SELECT 1 FROM workflow_triggers
    WHERE workflow_triggers.workflow_definition_id = 'scheduled-task:' || CAST(scheduled_tasks.id AS TEXT)
);
