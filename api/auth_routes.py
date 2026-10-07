"""소셜 로그인 엔드포인트.

앱 → (구글·애플·네이버·카카오 SDK로 토큰 획득) → POST /v1/auth/{provider} → 우리 액세스·갱신 토큰
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import CurrentUser, current_user
from .db import get_conn
from .providers import PROVIDERS, ProviderError
from .schemas import Problem
from .tokens import issue_access, issue_refresh, revoke_refresh, rotate_refresh
from .apple_revocation import DeleteAccountIn, revoke_for_account, prepare_grant, save_grant

router = APIRouter(prefix="/v1", tags=["auth"])
Provider = Literal["google", "apple", "naver", "kakao"]


class LoginIn(BaseModel):
    token: str = Field(min_length=1, max_length=16000, description="구글·애플: ID 토큰(JWT). 네이버·카카오: 액세스 토큰")
    nonce: str | None = Field(None, max_length=256, description="구글·애플: 요청 때 쓴 nonce (재생 공격 방지, 선택)")
    name: str | None = Field(None, max_length=200, description="애플: 첫 로그인 때만 앱이 받는 이름")
    authorization_code: str | None = Field(None, max_length=4096, description="Apple 승인 코드: 서버에서 교환 후 암호화 보관")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="액세스 토큰 수명(초)")
    user_id: str
    is_new: bool = Field(description="이번 로그인으로 계정이 새로 만들어졌는지")
    profile_exists: bool = Field(description="false면 온보딩 화면으로")


class RefreshIn(BaseModel):
    refresh_token: str


class IdentityOut(BaseModel):
    provider: Provider
    email: str | None
    display_name: str | None
    last_login_at: str


def _verify(request: Request, provider: str, body: LoginIn):
    verifier = request.app.state.verifiers.get(provider)
    if verifier is None:
        raise HTTPException(503, f"{provider} 로그인이 아직 설정되지 않았어요")
    try:
        return verifier.verify(body.token, body.nonce, body.name)
    except ProviderError as e:
        raise HTTPException(401, str(e))


def _pair(conn, request: Request, user_id: str, is_new: bool) -> dict:
    settings = request.app.state.settings
    with conn.cursor() as cur:
        cur.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        is_admin = cur.fetchone()[0]
        cur.execute("SELECT 1 FROM user_profiles WHERE user_id = %s", (user_id,))
        profile_exists = cur.fetchone() is not None
    access, ttl = issue_access(user_id, is_admin, settings)
    refresh = issue_refresh(conn, user_id, settings, user_agent=request.headers.get("user-agent"))
    return {"access_token": access, "refresh_token": refresh, "expires_in": ttl,
            "user_id": user_id, "is_new": is_new, "profile_exists": profile_exists}


# 고정 경로가 /auth/{provider} 보다 먼저 와야 한다
@router.get('/auth/providers')
def configured_providers(request: Request):
    return {'providers': list(request.app.state.verifiers), 'development': request.app.state.settings.dev_login}


@router.post("/auth/refresh", response_model=TokenPair, responses={401: {"model": Problem}})
def refresh(body: RefreshIn, request: Request, conn=Depends(get_conn)):
    """갱신 토큰으로 새 토큰 쌍. 갱신 토큰은 한 번 쓰면 새것으로 바뀐다."""
    rotated = rotate_refresh(conn, body.refresh_token, request.app.state.settings, request.headers.get("user-agent"))
    if not rotated:
        raise HTTPException(401, "다시 로그인해 주세요")
    user_id, new_refresh = rotated
    with conn.cursor() as cur:
        cur.execute("SELECT is_admin, deleted_at FROM users WHERE id = %s", (user_id,))
        is_admin, deleted = cur.fetchone()
        if deleted:
            raise HTTPException(401, "탈퇴한 계정이에요")
        cur.execute("SELECT 1 FROM user_profiles WHERE user_id = %s", (user_id,))
        profile_exists = cur.fetchone() is not None
    access, ttl = issue_access(user_id, is_admin, request.app.state.settings)
    return {"access_token": access, "refresh_token": new_refresh, "expires_in": ttl,
            "user_id": user_id, "is_new": False, "profile_exists": profile_exists}


@router.post("/auth/logout", status_code=204)
def logout(body: RefreshIn, conn=Depends(get_conn)):
    """이 기기의 갱신 토큰을 무효화. 액세스 토큰은 수명(기본 1시간)이 끝나면 자동으로 만료"""
    revoke_refresh(conn, body.refresh_token)


@router.post("/auth/{provider}", response_model=TokenPair,
             responses={401: {"model": Problem}, 503: {"model": Problem}})
def login(provider: Provider, body: LoginIn, request: Request, conn=Depends(get_conn)):
    """서비스 토큰을 검증하고 우리 토큰을 발급. 처음이면 계정을 만든다."""
    ident = _verify(request, provider, body)
    grant = prepare_grant(request, provider, ident, body)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (provider + ":" + ident.provider_user_id,))
        cur.execute("""SELECT i.user_id::text, u.deleted_at FROM auth_identities i JOIN users u ON u.id = i.user_id
                        WHERE i.provider = %s AND i.provider_user_id = %s""", (provider, ident.provider_user_id))
        row = cur.fetchone()
        if row and row[1] is None:
            user_id, is_new = row[0], False
            cur.execute("""UPDATE auth_identities SET last_login_at = now(),
                                  email = COALESCE(%s, email), display_name = COALESCE(%s, display_name)
                            WHERE provider = %s AND provider_user_id = %s""",
                        (ident.email, ident.name, provider, ident.provider_user_id))
        else:
            if row:                                                     # 탈퇴한 계정의 흔적 → 새 계정으로
                cur.execute("DELETE FROM auth_identities WHERE provider = %s AND provider_user_id = %s",
                            (provider, ident.provider_user_id))
            cur.execute("INSERT INTO users DEFAULT VALUES RETURNING id::text")
            user_id, is_new = cur.fetchone()[0], True
            cur.execute("""INSERT INTO auth_identities (user_id, provider, provider_user_id, email, display_name)
                           VALUES (%s, %s, %s, %s, %s)""", (user_id, provider, ident.provider_user_id, ident.email, ident.name))
    save_grant(conn, user_id, grant)
    return _pair(conn, request, user_id, is_new)


@router.get("/me/identities", response_model=list[IdentityOut], tags=["me"])
def identities(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("""SELECT provider::text, email, display_name, last_login_at::text
                         FROM auth_identities WHERE user_id = %s ORDER BY created_at""", (user.id,))
        return [dict(zip(("provider", "email", "display_name", "last_login_at"), r)) for r in cur.fetchall()]


@router.post("/me/identities/{provider}", status_code=204, tags=["me"],
             responses={401: {"model": Problem}, 409: {"model": Problem}})
def link_identity(provider: Provider, body: LoginIn, request: Request,
                  user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    """로그인된 계정에 다른 로그인 수단을 추가"""
    ident = _verify(request, provider, body)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user.id,))
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (provider + ":" + ident.provider_user_id,))
        cur.execute("SELECT user_id::text FROM auth_identities WHERE provider = %s AND provider_user_id = %s",
                    (provider, ident.provider_user_id))
        row = cur.fetchone()
        if row and row[0] != user.id:
            raise HTTPException(409, "이미 다른 계정에 연결된 로그인이에요")
        cur.execute('SELECT provider_user_id FROM auth_identities WHERE user_id=%s AND provider=%s', (user.id, provider))
        existing = cur.fetchone()
        if existing and existing[0] != ident.provider_user_id:
            raise HTTPException(409, '이 서비스의 계정이 이미 연결되어 있어요. 먼저 연결을 해제해 주세요')
        grant = prepare_grant(request, provider, ident, body)
        if not row:
            cur.execute("""INSERT INTO auth_identities (user_id, provider, provider_user_id, email, display_name)
                           VALUES (%s, %s, %s, %s, %s)""", (user.id, provider, ident.provider_user_id, ident.email, ident.name))
        save_grant(conn, user.id, grant)


@router.delete("/me/identities/{provider}", status_code=204, tags=["me"], responses={409: {"model": Problem}})
def unlink_identity(provider: Provider, request: Request, body: DeleteAccountIn | None = None, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (user.id,))
        cur.execute('SELECT 1 FROM auth_identities WHERE user_id=%s AND provider=%s', (user.id,provider))
        if not cur.fetchone(): raise HTTPException(404, '연결된 로그인이 아니에요')
        cur.execute("SELECT count(DISTINCT provider) FROM auth_identities WHERE user_id = %s", (user.id,))
        if cur.fetchone()[0] <= 1:
            raise HTTPException(409, "마지막 로그인 수단은 해제할 수 없어요. 탈퇴를 이용해 주세요")
        if provider == 'apple': revoke_for_account(request, conn, user.id, body)
        if provider == 'apple': cur.execute('DELETE FROM apple_grants WHERE user_id=%s', (user.id,))
        cur.execute("DELETE FROM auth_identities WHERE user_id = %s AND provider = %s", (user.id, provider))
        if cur.rowcount == 0:
            raise HTTPException(404, "연결된 로그인이 아니에요")


PROVIDER_LABELS = {"google": "구글", "apple": "애플", "naver": "네이버", "kakao": "카카오"}
assert set(PROVIDER_LABELS) == set(PROVIDERS)
