CREATE TABLE IF NOT EXISTS workflow_candidate_sets (
    id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    workflow_node_run_id INTEGER,
    source TEXT NOT NULL,
    sort_order TEXT NOT NULL,
    total_count INTEGER NOT NULL DEFAULT 0,
    config_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id),
    FOREIGN KEY (workflow_node_run_id) REFERENCES workflow_node_runs(id)
);

CREATE TABLE IF NOT EXISTS workflow_candidate_artworks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    set_id TEXT NOT NULL,
    artist_id TEXT NOT NULL,
    artwork_id TEXT NOT NULL,
    source TEXT NOT NULL,
    position INTEGER NOT NULL,
    sort_key INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (set_id, artwork_id),
    FOREIGN KEY (set_id) REFERENCES workflow_candidate_sets(id),
    FOREIGN KEY (artwork_id) REFERENCES artworks(id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_candidate_sets_run_id
    ON workflow_candidate_sets(workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_workflow_candidate_artworks_set_id
    ON workflow_candidate_artworks(set_id, position);

CREATE INDEX IF NOT EXISTS idx_workflow_candidate_artworks_artwork_id
    ON workflow_candidate_artworks(artwork_id);
