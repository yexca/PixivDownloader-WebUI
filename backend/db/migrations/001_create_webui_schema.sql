CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    account TEXT,
    profile_url TEXT NOT NULL,
    avatar_url TEXT,
    comment TEXT,
    legacy_last_download_id TEXT,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artworks (
    id TEXT PRIMARY KEY,
    artist_id TEXT NOT NULL,
    title TEXT,
    type TEXT,
    caption TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    width INTEGER,
    height INTEGER,
    sanity_level INTEGER,
    restrict_value INTEGER,
    tags_json TEXT NOT NULL DEFAULT '[]',
    pixiv_created_at TEXT,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

CREATE TABLE IF NOT EXISTS artwork_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artwork_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    original_url TEXT NOT NULL,
    local_path TEXT,
    file_name TEXT NOT NULL,
    size_bytes INTEGER,
    status TEXT NOT NULL,
    downloaded_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (artwork_id, page_index),
    FOREIGN KEY (artwork_id) REFERENCES artworks(id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    input_user_id TEXT,
    input_artwork_id TEXT,
    artist_id TEXT,
    total_files INTEGER NOT NULL DEFAULT 0,
    completed_files INTEGER NOT NULL DEFAULT 0,
    skipped_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

