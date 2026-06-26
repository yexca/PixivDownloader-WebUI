CREATE TABLE IF NOT EXISTS local_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artist_local_tags (
    artist_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (artist_id, tag_id),
    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES local_tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_artist_local_tags_artist_id
    ON artist_local_tags(artist_id);

CREATE INDEX IF NOT EXISTS idx_artist_local_tags_tag_id
    ON artist_local_tags(tag_id);
