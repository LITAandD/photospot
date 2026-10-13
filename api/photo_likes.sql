-- Independent of private account/profile tables; also usable by the public web preview.
CREATE TABLE IF NOT EXISTS photo_likes (
    place_id text NOT NULL,
    photo_id text NOT NULL,
    voter_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (place_id, photo_id, voter_hash)
);
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
