"""인증: 소셜 로그인(/v1/auth/*)으로 발급한 액세스 토큰(JWT)을 검증한다.

토큰 claims: sub = 사용자 UUID, typ = "access", role = "admin" (users.is_admin 인 경우에만 발급)
"""
import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request

from .db import get_conn


@dataclass
class CurrentUser:
    id: str
    is_admin: bool


def current_user(request: Request, conn=Depends(get_conn)) -> CurrentUser:
    settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "인증 토큰이 필요해요")
    try:
        claims = jwt.decode(header[7:], settings.jwt_secret, algorithms=[settings.jwt_algorithm],
                            options={"require": ["sub", "exp", "iat", "jti", "typ"]})
        user_id = str(uuid.UUID(claims["sub"]))
        if claims.get("typ") != "access":
            raise ValueError("access token required")
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "유효하지 않은 토큰이에요")
    with conn.cursor() as cur:
        cur.execute("SELECT deleted_at, is_admin FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if row is None or row[0] is not None:
            raise HTTPException(401, "탈퇴한 계정이에요")
    return CurrentUser(user_id, bool(row[1]))


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(403, "검수자 권한이 필요해요")
    return user
