-- Encryption key stays in the server secret store, never in this database.
CREATE TABLE apple_grants (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    encrypted_token text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
