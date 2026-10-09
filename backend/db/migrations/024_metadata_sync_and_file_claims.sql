ALTER TABLE artists ADD COLUMN metadata_synced_artwork_id TEXT;

CREATE TABLE artwork_file_download_claims (
    file_id INTEGER PRIMARY KEY REFERENCES artwork_files(id) ON DELETE CASCADE,
    owner TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    previous_error_message TEXT
);
