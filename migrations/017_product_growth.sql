-- Account links, first-party sponsorships, store entitlements and reviewed feedback.
CREATE TABLE social_connections (
 user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 instagram_id text NOT NULL UNIQUE, username text NOT NULL,
 connected_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE social_oauth_states (
 state_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL, consumed_at timestamptz
);
CREATE TABLE app_feedback (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 category text NOT NULL CHECK(category IN ('bug','idea','place','other')),
 message text NOT NULL CHECK(length(message) BETWEEN 5 AND 2000),
 ai_consent boolean NOT NULL DEFAULT false,
 reviewed_text text, reviewed_by uuid REFERENCES users(id), reviewed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX app_feedback_user_created ON app_feedback(user_id,created_at);
CREATE TABLE feedback_triages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), feedback_ids uuid[] NOT NULL,
 result jsonb NOT NULL, model text NOT NULL,
 status text NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','planned','done','dismissed')),
 review_note text NOT NULL DEFAULT '', reviewed_by uuid REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE growth_audit (
 id bigserial PRIMARY KEY, actor_id uuid REFERENCES users(id), action text NOT NULL,
 target_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE billing_entitlements (
 user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 premium_until timestamptz, management_url text, checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sponsored_campaigns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), place_id uuid NOT NULL,
 sponsor text NOT NULL, headline text NOT NULL,
 placement text NOT NULL CHECK(placement IN ('banner','priority')),
 starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL,
 approved boolean NOT NULL DEFAULT false, created_by uuid REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(ends_at > starts_at)
);
CREATE TABLE campaign_events (
 campaign_id uuid REFERENCES sponsored_campaigns(id) ON DELETE CASCADE,
 user_id uuid REFERENCES users(id) ON DELETE CASCADE,
 kind text NOT NULL CHECK(kind IN ('impression','click')), day date NOT NULL DEFAULT current_date,
 PRIMARY KEY(campaign_id,user_id,kind,day)
);
