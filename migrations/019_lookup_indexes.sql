-- /media/{path} checks every request against photos.storage_path.
CREATE INDEX IF NOT EXISTS photos_storage_path_idx ON photos (storage_path);
-- Upload removal on consent withdrawal and account deletion.
CREATE INDEX IF NOT EXISTS photos_uploader_idx ON photos (uploader_id) WHERE uploader_id IS NOT NULL;
-- Refresh-token reuse revokes the whole login family.
CREATE INDEX IF NOT EXISTS refresh_tokens_family_idx ON refresh_tokens (family_id) WHERE revoked_at IS NULL;
-- The worker re-queues jobs whose worker stopped while running.
CREATE INDEX IF NOT EXISTS jobs_running_idx ON jobs (locked_at) WHERE status = 'running';
