ALTER TABLE artists
    ADD COLUMN account_status TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE artists
    ADD COLUMN account_status_checked_at TEXT;

ALTER TABLE artists
    ADD COLUMN account_status_reason TEXT;

ALTER TABLE artists
    ADD COLUMN remote_latest_artwork_id TEXT;

ALTER TABLE artists
    ADD COLUMN remote_latest_checked_at TEXT;

CREATE INDEX IF NOT EXISTS idx_artists_account_status
    ON artists(account_status);

CREATE INDEX IF NOT EXISTS idx_artists_remote_latest_checked_at
    ON artists(remote_latest_checked_at);
