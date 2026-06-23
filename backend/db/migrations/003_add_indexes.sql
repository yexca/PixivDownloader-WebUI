CREATE INDEX IF NOT EXISTS idx_artworks_artist_id ON artworks(artist_id);
CREATE INDEX IF NOT EXISTS idx_artwork_files_artwork_id ON artwork_files(artwork_id);
CREATE INDEX IF NOT EXISTS idx_artwork_files_status ON artwork_files(status);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);

