-- Catalog recommendations are not persisted per user: their IDs are public catalog
-- row IDs, so visit feedback is kept per user and public OSM place UUID.
CREATE TABLE IF NOT EXISTS catalog_feedback (
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place_id        uuid NOT NULL,
    visited         boolean,
    rating          smallint CHECK (rating BETWEEN 1 AND 5),
    tag_corrections jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, place_id)
);
CREATE INDEX IF NOT EXISTS catalog_feedback_place_idx ON catalog_feedback (place_id);
