CREATE TABLE bookmarks (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    place_id uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, place_id)
);
CREATE INDEX bookmarks_user_created_idx ON bookmarks (user_id, created_at DESC);
