-- Independent of private account/profile tables; also usable by the public web preview.
CREATE TABLE IF NOT EXISTS photo_likes (
    place_id text NOT NULL,
    photo_id text NOT NULL,
    voter_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (place_id, photo_id, voter_hash)
);
CREATE INDEX IF NOT EXISTS photo_likes_voter_idx ON photo_likes (voter_hash);
CREATE TABLE IF NOT EXISTS liked_photo_evidence (
    place_id text NOT NULL,
    photo_id text NOT NULL,
    photo_url text NOT NULL,
    source_url text NOT NULL,
    attributes jsonb NOT NULL,
    method text NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (place_id, photo_id)
);
-- A deletion tombstone stops an already-authenticated, in-flight request from
-- recreating a deleted account's preference after the account transaction ends.
CREATE TABLE IF NOT EXISTS revoked_photo_voters (
    voter_hash text PRIMARY KEY,
    revoked_at timestamptz NOT NULL DEFAULT now()
);
