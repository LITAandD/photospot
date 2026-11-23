CREATE TABLE IF NOT EXISTS visitor_photos (
 id TEXT PRIMARY KEY,
 place_id TEXT NOT NULL,
 token_hash TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 credit TEXT NOT NULL,
 caption TEXT NOT NULL,
 consent TEXT NOT NULL,
 policy_snapshot TEXT NOT NULL,
 faces TEXT NOT NULL,
 image BYTEA,
 image_sha256 TEXT NOT NULL,
 image_bytes INTEGER NOT NULL CHECK (image_bytes BETWEEN 0 AND 2097152),
 width INTEGER NOT NULL,
 height INTEGER NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('pending','approved','rejected','withdrawn')),
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 rate_key TEXT NOT NULL,
 reviewer TEXT NOT NULL DEFAULT '',
 review_checks TEXT NOT NULL DEFAULT '{}',
 reviewed_at TEXT,
 note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS visitor_photos_place ON visitor_photos(place_id,state,expires_at);
CREATE INDEX IF NOT EXISTS visitor_photos_expiry ON visitor_photos(expires_at);
CREATE INDEX IF NOT EXISTS visitor_photos_rate ON visitor_photos(rate_key);

