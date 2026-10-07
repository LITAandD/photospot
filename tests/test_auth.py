"""소셜 로그인 테스트 (DATABASE_URL 필요). 외부 서비스는 가짜 키·가짜 응답으로 대체."""
import hashlib
import os
import sys
import time
import uuid
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.config import Settings                                        # noqa: E402
from api.main import create_app                                         # noqa: E402
from api.providers import AppleVerifier, GoogleVerifier, KakaoVerifier, NaverVerifier, ProviderError  # noqa: E402

DSN = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL 없음")
SECRET = "auth-test-secret"
RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@dataclass
class FakeKey:
    key: object


class FakeJwks:                       # PyJWKClient 대역: 항상 우리 테스트 공개키를 돌려준다
    def get_signing_key_from_jwt(self, token):
        return FakeKey(RSA.public_key())


def id_token(iss, aud, sub, key=RSA, **extra):
    now = int(time.time())
    return jwt.encode({"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + 600, **extra}, key, algorithm="RS256")


def google_token(sub="g-1", **extra):
    return id_token("https://accounts.google.com", "ios-client-id", sub, email=f"{sub}@gmail.com", email_verified=True, name="구글 사용자", **extra)


def apple_token(sub="a-1", **extra):
    return id_token("https://appleid.apple.com", "app.photospot", sub, email=f"{sub}@privaterelay.appleid.com", email_verified="true", **extra)

def apple_body(sub):
    nonce=uuid.uuid4().hex
    token=apple_token(sub,nonce=hashlib.sha256(nonce.encode()).hexdigest())
    return {'token':token,'nonce':nonce,'authorization_code':token}


NAVER_OK = {"resultcode": "00", "response": {"id": "n-1", "email": "n1@naver.com", "nickname": "네이버 사용자"}}
KAKAO_INFO = {"app_id": 12345}
KAKAO_ME = {"id": 99, "kakao_account": {"email": "k1@kakao.com", "is_email_valid": True, "is_email_verified": True,
                                       "profile": {"nickname": "카카오 사용자"}}}


def fake_http(responses):
    def get(url, bearer=None, timeout=10):
        if bearer != "valid":
            raise RuntimeError("401")
        return responses[url]
    return get


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path_factory.mktemp("s")),
                        google_client_ids=["ios-client-id", "android-client-id"], apple_audiences=["app.photospot"], kakao_app_id=12345,
                        apple_client_id='app.photospot',apple_token_encryption_key=Fernet.generate_key().decode())
    verifiers = {
        "google": GoogleVerifier(settings.google_client_ids, jwks_client=FakeJwks()),
        "apple": AppleVerifier(settings.apple_audiences, jwks_client=FakeJwks()),
        "naver": NaverVerifier(http_json=fake_http({"https://openapi.naver.com/v1/nid/me": NAVER_OK})),
        "kakao": KakaoVerifier(12345, http_json=fake_http({"https://kapi.kakao.com/v1/user/access_token_info": KAKAO_INFO,
                                                          "https://kapi.kakao.com/v2/user/me": KAKAO_ME})),
    }
    app=create_app(settings, verifiers=verifiers)
    app.state.apple_revoker.credentials=lambda:{'client_id':'app.photospot','client_secret':'test-only'}
    app.state.apple_revoker.transport=lambda endpoint,fields: {'id_token':fields['code'],'refresh_token':'test-refresh'} if endpoint=='token' else {}
    return TestClient(app)


def bearer(pair):
    return {"Authorization": f"Bearer {pair['access_token']}"}


# ---------------------------------------------------------------------------
def test_google_login_creates_user_then_reuses_it(client):
    sub = f"g-{uuid.uuid4().hex[:8]}"
    first = client.post("/v1/auth/google", json={"token": google_token(sub)}).json()
    assert first["is_new"] is True and first["profile_exists"] is False and first["token_type"] == "bearer"
    me = client.get("/v1/me/profile", headers=bearer(first))
    assert me.status_code == 200                                              # 우리 액세스 토큰으로 API 사용
    second = client.post("/v1/auth/google", json={"token": google_token(sub)}).json()
    assert second["is_new"] is False and second["user_id"] == first["user_id"]
    ids = client.get("/v1/me/identities", headers=bearer(second)).json()
    assert ids == [{"provider": "google", "email": f"{sub}@gmail.com", "display_name": "구글 사용자", "last_login_at": ids[0]["last_login_at"]}]


def test_google_rejects_wrong_audience_signature_and_nonce(client):
    bad_aud = id_token("https://accounts.google.com", "someone-elses-app", "g-x")
    assert client.post("/v1/auth/google", json={"token": bad_aud}).status_code == 401
    forged = id_token("https://accounts.google.com", "ios-client-id", "g-x", key=OTHER_RSA)
    assert client.post("/v1/auth/google", json={"token": forged}).status_code == 401
    assert client.post("/v1/auth/google", json={"token": google_token("g-n", nonce="abc"), "nonce": "xyz"}).status_code == 401
    assert client.post("/v1/auth/google", json={"token": google_token("g-n", nonce="abc"), "nonce": "abc"}).status_code == 200


def test_apple_login_keeps_first_login_name_and_hashed_nonce(client):
    sub = f"a-{uuid.uuid4().hex[:8]}"
    nonce = "n-" + uuid.uuid4().hex
    tok = apple_token(sub, nonce=hashlib.sha256(nonce.encode()).hexdigest())
    pair = client.post("/v1/auth/apple", json={"token": tok, "nonce": nonce, "name": "애플 사용자", "authorization_code":tok}).json()
    assert pair["is_new"]
    again = client.post("/v1/auth/apple", json=apple_body(sub)).json()     # 두 번째부턴 이름 없음
    ids = client.get("/v1/me/identities", headers=bearer(again)).json()
    assert ids[0]["display_name"] == "애플 사용자" and ids[0]["email"].endswith("privaterelay.appleid.com")


def test_naver_and_kakao(client):
    naver = client.post("/v1/auth/naver", json={"token": "valid"}).json()
    assert client.get("/v1/me/identities", headers=bearer(naver)).json()[0]["display_name"] == "네이버 사용자"
    assert client.post("/v1/auth/naver", json={"token": "expired"}).status_code == 401
    kakao = client.post("/v1/auth/kakao", json={"token": "valid"}).json()
    assert client.get("/v1/me/identities", headers=bearer(kakao)).json()[0]["email"] == "k1@kakao.com"
    wrong_app = KakaoVerifier(777, http_json=fake_http({"https://kapi.kakao.com/v1/user/access_token_info": KAKAO_INFO,
                                                        "https://kapi.kakao.com/v2/user/me": KAKAO_ME}))
    with pytest.raises(ProviderError):
        wrong_app.verify("valid")                                               # 다른 앱의 카카오 토큰


def test_unconfigured_provider_returns_503(tmp_path):
    settings = Settings(database_url=DSN, jwt_secret=SECRET, storage_root=str(tmp_path))
    c = TestClient(create_app(settings, verifiers={}))
    assert c.post("/v1/auth/google", json={"token": "x"}).status_code == 503


def test_refresh_rotation_and_reuse_detection(client):
    pair = client.post("/v1/auth/google", json={"token": google_token(f"g-{uuid.uuid4().hex[:8]}")}).json()
    r1 = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).json()
    assert r1["refresh_token"] != pair["refresh_token"] and r1["user_id"] == pair["user_id"]
    assert client.get("/v1/me/profile", headers=bearer(r1)).status_code == 200
    # 옛 갱신 토큰을 다시 쓰면(탈취 의심) 실패하고, 새 토큰까지 함께 무효화된다
    assert client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    assert client.post("/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]}).status_code == 401


def test_logout_and_refresh_token_is_not_an_access_token(client):
    pair = client.post("/v1/auth/google", json={"token": google_token(f"g-{uuid.uuid4().hex[:8]}")}).json()
    assert client.post("/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}).status_code == 204
    assert client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    assert client.get("/v1/me/profile", headers={"Authorization": "Bearer " + pair["refresh_token"]}).status_code == 401
    refresh_as_jwt = jwt.encode({"sub": pair["user_id"], "typ": "refresh"}, SECRET, algorithm="HS256")
    assert client.get("/v1/me/profile", headers={"Authorization": "Bearer " + refresh_as_jwt}).status_code == 401


def test_link_and_unlink(client):
    g = f"g-{uuid.uuid4().hex[:8]}"
    pair = client.post("/v1/auth/google", json={"token": google_token(g)}).json()
    assert client.delete("/v1/me/identities/google", headers=bearer(pair)).status_code == 409   # 마지막 수단
    a = f"a-{uuid.uuid4().hex[:8]}"
    assert client.post("/v1/me/identities/apple", headers=bearer(pair), json=apple_body(a)).status_code == 204
    assert {i["provider"] for i in client.get("/v1/me/identities", headers=bearer(pair)).json()} == {"google", "apple"}
    via_apple = client.post("/v1/auth/apple", json=apple_body(a)).json()
    assert via_apple["user_id"] == pair["user_id"]                            # 애플로 들어와도 같은 계정
    other = client.post("/v1/auth/google", json={"token": google_token(f"g-{uuid.uuid4().hex[:8]}")}).json()
    assert client.post("/v1/me/identities/apple", headers=bearer(other), json={"token": apple_token(a)}).status_code == 409
    assert client.delete("/v1/me/identities/google", headers=bearer(pair)).status_code == 204


def test_delete_account_clears_identities_and_blocks_refresh(client):
    g = f"g-{uuid.uuid4().hex[:8]}"
    pair = client.post("/v1/auth/google", json={"token": google_token(g)}).json()
    assert client.delete("/v1/me", headers=bearer(pair)).status_code == 204
    assert client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    assert client.get("/v1/me/profile", headers=bearer(pair)).status_code == 401
    fresh = client.post("/v1/auth/google", json={"token": google_token(g)}).json()   # 다시 가입하면 새 계정
    assert fresh["is_new"] and fresh["user_id"] != pair["user_id"]
