CREATE TABLE IF NOT EXISTS pic (
    ID TEXT PRIMARY KEY,
    name TEXT,
    downloadedDate TEXT,
    lastDownloadID TEXT,
    url TEXT
);

INSERT OR IGNORE INTO artists (
    id,
    name,
    profile_url,
    legacy_last_download_id,
    last_checked_at,
    created_at,
    updated_at
)
SELECT
    ID,
    COALESCE(NULLIF(name, ''), ID),
    COALESCE(NULLIF(url, ''), 'https://www.pixiv.net/users/' || ID),
    lastDownloadID,
    downloadedDate,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM pic
WHERE ID IS NOT NULL;

