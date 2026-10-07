"""소셜 로그인 토큰 검증.

- 구글·애플: 앱이 받은 ID 토큰(JWT)을 각 사의 공개키(JWKS)로 서명 검증하고, 대상(aud)·발급자(iss)를 확인
- 네이버·카카오: 앱이 받은 액세스 토큰으로 사용자 정보 API를 호출해 확인 (카카오는 앱 ID까지 대조)
네트워크 호출은 주입 가능해서 테스트에서는 가짜 키·가짜 응답으로 검증한다.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import jwt

PROVIDERS = ("google", "apple", "naver", "kakao")


class ProviderError(Exception):
    """토큰이 유효하지 않거나 우리 앱용이 아님 → 401"""


@dataclass
class Identity:
    provider: str
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    email_verified: bool = False


class Verifier(Protocol):
    def verify(self, token: str, nonce: str | None = None, name: str | None = None) -> Identity: ...


def _http_json(url: str, bearer: str | None = None, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"} if bearer else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class _JwtVerifier:
    issuer: tuple[str, ...]
    jwks_url: str
    provider: str

    def __init__(self, audiences: list[str], jwks_client=None):
        if not audiences:
            raise ValueError(f"{self.provider} 클라이언트 ID가 설정되지 않았어요")
        self.audiences = audiences
        self._jwks = jwks_client or jwt.PyJWKClient(self.jwks_url, cache_keys=True)

    def _decode(self, token: str) -> dict:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audiences,
                                options={"require": ["exp", "iat", "sub", "iss", "aud"]})
        except jwt.PyJWTError as e:
            raise ProviderError(f"{self.provider} 토큰 검증 실패: {e}") from e
        if claims.get("iss") not in self.issuer:                  # 발급자는 직접 대조 (여러 값 허용)
            raise ProviderError(f"{self.provider} 토큰 발급자가 다릅니다")
        return claims


class GoogleVerifier(_JwtVerifier):
    provider = "google"
    issuer = ("https://accounts.google.com", "accounts.google.com")
    jwks_url = "https://www.googleapis.com/oauth2/v3/certs"

    def verify(self, token, nonce=None, name=None) -> Identity:
        c = self._decode(token)
        if nonce is not None and c.get("nonce") != nonce:
            raise ProviderError("nonce 불일치")
        return Identity("google", c["sub"], c.get("email"), c.get("name") or name, bool(c.get("email_verified")))


class AppleVerifier(_JwtVerifier):
    provider = "apple"
    issuer = ("https://appleid.apple.com",)
    jwks_url = "https://appleid.apple.com/auth/keys"

    def verify(self, token, nonce=None, name=None) -> Identity:
        c = self._decode(token)
        if nonce is not None:                                   # 애플은 nonce의 SHA-256을 담는다
            if c.get("nonce") != hashlib.sha256(nonce.encode()).hexdigest():
                raise ProviderError("nonce 불일치")
        verified = c.get("email_verified") in (True, "true")
        return Identity("apple", c["sub"], c.get("email"), name, verified)     # 이름은 첫 로그인 때 앱이 넘겨줌


class NaverVerifier:
    def __init__(self, http_json=_http_json):
        self._get = http_json

    def verify(self, token, nonce=None, name=None) -> Identity:
        try:
            body = self._get("https://openapi.naver.com/v1/nid/me", bearer=token)
        except Exception as e:
            raise ProviderError("네이버 토큰 확인 실패") from e
        if body.get("resultcode") != "00":
            raise ProviderError("네이버 토큰이 유효하지 않아요")
        r = body["response"]
        return Identity("naver", r["id"], r.get("email"), r.get("name") or r.get("nickname"), bool(r.get("email")))


class KakaoVerifier:
    def __init__(self, app_id: int | None, http_json=_http_json):
        self.app_id, self._get = app_id, http_json

    def verify(self, token, nonce=None, name=None) -> Identity:
        try:
            if self.app_id is not None:                              # 우리 앱에서 발급된 토큰인지
                info = self._get("https://kapi.kakao.com/v1/user/access_token_info", bearer=token)
                if int(info.get("app_id", -1)) != self.app_id:
                    raise ProviderError("우리 앱용 카카오 토큰이 아니에요")
            me = self._get("https://kapi.kakao.com/v2/user/me", bearer=token)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("카카오 토큰 확인 실패") from e
        acct = me.get("kakao_account") or {}
        email = acct.get("email") if acct.get("is_email_valid") and acct.get("is_email_verified") else None
        nick = (acct.get("profile") or {}).get("nickname")
        return Identity("kakao", str(me["id"]), email, nick, email is not None)


class DevVerifier:
    """개발 전용: 토큰 'dev:<아무 ID>' 를 그대로 믿는다. DEV_LOGIN=1 일 때만 구글 자리에 끼워진다.
    Expo Go처럼 네이티브 SDK를 못 쓰는 환경에서 앱을 돌려보기 위한 것. 운영에서 절대 켜지 말 것."""

    def verify(self, token, nonce=None, name=None) -> Identity:
        if not token.startswith("dev:"):
            raise ProviderError("개발용 토큰은 'dev:<id>' 형식이에요")
        return Identity("google", "dev-" + token[4:], f"{token[4:]}@dev.local", name or "개발 사용자", True)


def build_verifiers(settings) -> dict[str, Verifier]:
    """설정된 서비스만 활성화. 설정이 없는 서비스는 401이 아니라 503으로 안내된다."""
    out: dict[str, Verifier] = {}
    if settings.dev_login:
        out["google"] = DevVerifier()
    if settings.google_client_ids:
        out["google"] = GoogleVerifier(settings.google_client_ids)
    if settings.apple_audiences:
        out["apple"] = AppleVerifier(settings.apple_audiences)
    if settings.naver_login_enabled: out["naver"] = NaverVerifier()
    if settings.kakao_app_id: out["kakao"] = KakaoVerifier(settings.kakao_app_id)
    return out
