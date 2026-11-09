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
-- Anonymous funnel events: random client session ids only; no IP, user agent,
-- account id or query strings. Dropped (HTTP 204) when this store is absent.
CREATE TABLE IF NOT EXISTS analytics_events (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    event text NOT NULL,
    route text NOT NULL,
    session_id text NOT NULL,
    utm jsonb NOT NULL DEFAULT '{}'::jsonb,
    props jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS analytics_events_event_idx ON analytics_events (event, created_at);
CREATE INDEX IF NOT EXISTS analytics_events_session_idx ON analytics_events (session_id, created_at);
