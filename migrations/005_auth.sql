-- =====================================================================
-- 005: 소셜 로그인(구글·애플·네이버·카카오)과 토큰 갱신 (004 이후 실행)
-- =====================================================================
CREATE TYPE auth_provider_t AS ENUM ('google', 'apple', 'naver', 'kakao');

-- 한 사용자에 여러 로그인 수단을 연결할 수 있다
CREATE TABLE auth_identities (
    id                bigserial PRIMARY KEY,
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider          auth_provider_t NOT NULL,
    provider_user_id  text NOT NULL,                 -- 각 서비스가 주는 고유 ID (sub / id)
    email             text,                          -- 서비스가 준 경우만. 애플은 첫 로그인 때만 줌
    display_name      text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    last_login_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_user_id)
);
CREATE INDEX auth_identities_user_idx ON auth_identities (user_id);

-- 갱신 토큰: 원문은 저장하지 않고 해시만. 한 번 쓰면 새 토큰으로 교체(회전)하고, 재사용이 감지되면 계열 전체를 무효화
CREATE TABLE refresh_tokens (
    id           bigserial PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash   text NOT NULL UNIQUE,
    family_id    uuid NOT NULL,                      -- 로그인 한 번 = 계열 하나
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    replaced_by  bigint REFERENCES refresh_tokens(id),
    user_agent   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id) WHERE revoked_at IS NULL;

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
