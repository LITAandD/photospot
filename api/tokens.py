"""우리 서버가 발급하는 토큰.

- 액세스 토큰: 짧은 수명의 JWT (sub, typ=access, role). 서버가 직접 발급·검증하므로 HS256이면 충분
- 갱신 토큰: 임의의 긴 문자열. DB에는 해시만 저장. 쓸 때마다 새 토큰으로 교체(회전)하고,
  이미 교체된 토큰이 다시 오면(탈취 의심) 그 로그인 계열 전체를 무효화한다
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt


def issue_access(user_id: str, is_admin: bool, settings) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    ttl = settings.access_ttl_min * 60
    claims = {"sub": user_id, "typ": "access", "iat": now, "exp": now + timedelta(seconds=ttl), "jti": uuid.uuid4().hex}
    if is_admin:
        claims["role"] = "admin"
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm), ttl


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh(conn, user_id: str, settings, family_id: str | None = None,
                  user_agent: str | None = None, replaces: int | None = None) -> str:
    token = secrets.token_urlsafe(48)
    family = family_id or str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO refresh_tokens (user_id, token_hash, family_id, expires_at, user_agent)
                       VALUES (%s, %s, %s, now() + make_interval(days => %s), %s) RETURNING id""",
                    (user_id, _hash(token), family, settings.refresh_ttl_days, user_agent))
        new_id = cur.fetchone()[0]
        if replaces is not None:
            cur.execute("UPDATE refresh_tokens SET revoked_at = now(), replaced_by = %s WHERE id = %s", (new_id, replaces))
    return token


def rotate_refresh(conn, token: str, settings, user_agent: str | None = None) -> tuple[str, str] | None:
    """유효하면 (user_id, 새 갱신 토큰). 만료·무효·재사용이면 None (재사용은 계열 전체 무효화)."""
    with conn.cursor() as cur:
        cur.execute("""SELECT id, user_id::text, family_id::text, revoked_at, expires_at < now()
                         FROM refresh_tokens WHERE token_hash = %s FOR UPDATE""", (_hash(token),))
        row = cur.fetchone()
        if not row:
            return None
        rid, user_id, family, revoked_at, expired = row
        if revoked_at is not None:                                  # 이미 교체된 토큰의 재사용 → 탈취 의심
            cur.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE family_id = %s AND revoked_at IS NULL", (family,))
            conn.commit()                                           # 뒤이어 401을 돌려줘도(롤백) 무효화는 남아야 한다
            return None
        if expired:
            cur.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE id = %s", (rid,))
            conn.commit()
            return None
    return user_id, issue_refresh(conn, user_id, settings, family_id=family, user_agent=user_agent, replaces=rid)


def revoke_refresh(conn, token: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL", (_hash(token),))


def revoke_all(conn, user_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (user_id,))
