-- Catalog IDs are public OSM UUIDs and remain independent of curated scene IDs.
CREATE TABLE catalog_bookmarks (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id, place_id)
);
CREATE INDEX catalog_bookmarks_user_created ON catalog_bookmarks(user_id, created_at DESC);
