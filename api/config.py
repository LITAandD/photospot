import os
from dataclasses import dataclass, field
from .deployment import https_url


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.environ.get("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", "postgresql://localhost/photospot"))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("JWT_SECRET", "dev-only-secret-change-me"))
    jwt_algorithm: str = "HS256"
    storage_root: str = field(default_factory=lambda: os.environ.get("STORAGE_ROOT", "./storage"))
    max_upload_mb: int = 15
    max_radius_m: int = 50_000
    policy_version: str = "2026-09"
    recommendation_backend: str = field(default_factory=lambda: os.environ.get('RECOMMENDATION_BACKEND', 'catalog'))
    # 소셜 로그인 (쉼표로 여러 개). 구글은 iOS·Android·웹 클라이언트 ID를 모두, 애플은 번들 ID(+서비스 ID)
    google_client_ids: list[str] = field(default_factory=lambda: _csv("GOOGLE_CLIENT_IDS"))
    apple_audiences: list[str] = field(default_factory=lambda: _csv("APPLE_AUDIENCES"))
    apple_client_id: str = field(default_factory=lambda: os.environ.get('APPLE_CLIENT_ID',''))
    apple_team_id: str = field(default_factory=lambda: os.environ.get('APPLE_TEAM_ID',''))
    apple_key_id: str = field(default_factory=lambda: os.environ.get('APPLE_KEY_ID',''))
    apple_private_key_path: str = field(default_factory=lambda: os.environ.get('APPLE_PRIVATE_KEY_PATH',''))
    apple_token_encryption_key: str = field(default_factory=lambda: os.environ.get('APPLE_TOKEN_ENCRYPTION_KEY',''))
    kakao_app_id: int | None = field(default_factory=lambda: int(os.environ["KAKAO_APP_ID"]) if os.environ.get("KAKAO_APP_ID") else None)
    dev_login: bool = field(default_factory=lambda: os.environ.get("DEV_LOGIN") == "1")   # 개발 전용
    access_ttl_min: int = 60
    refresh_ttl_days: int = 60
    naver_login_enabled: bool = field(default_factory=lambda: os.environ.get('NAVER_LOGIN_ENABLED') == '1')
    instagram_client_id: str = field(default_factory=lambda: os.environ.get('INSTAGRAM_CLIENT_ID', ''))
    instagram_client_secret: str = field(default_factory=lambda: os.environ.get('INSTAGRAM_CLIENT_SECRET', ''))
    instagram_redirect_uri: str = field(default_factory=lambda: os.environ.get('INSTAGRAM_REDIRECT_URI', ''))
    openai_api_key: str = field(default_factory=lambda: os.environ.get('OPENAI_API_KEY', ''))
    feedback_model: str = field(default_factory=lambda: os.environ.get('FEEDBACK_MODEL', 'gpt-4o-mini'))
    revenuecat_secret_key: str = field(default_factory=lambda: os.environ.get('REVENUECAT_SECRET_KEY', ''))
    premium_entitlement: str = field(default_factory=lambda: os.environ.get('PREMIUM_ENTITLEMENT', 'photospot_plus'))
    cors_origins: list[str] = field(default_factory=lambda: _csv("CORS_ORIGINS") or ["http://localhost:8081"])

    def __post_init__(self):
        if self.instagram_client_id and (not self.instagram_client_secret or not https_url(self.instagram_redirect_uri)):
            raise ValueError('Instagram requires server secret and an HTTPS callback URL')
        if self.recommendation_backend not in {'catalog', 'scenes'}:
            raise ValueError('RECOMMENDATION_BACKEND must be catalog or scenes')
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test or production")
        if self.environment == "production":
            if self.apple_audiences and (not all((self.apple_client_id, self.apple_team_id, self.apple_key_id, self.apple_private_key_path, self.apple_token_encryption_key))
                                         or self.apple_client_id not in self.apple_audiences):
                raise ValueError('Apple login requires matching APPLE_CLIENT_ID and server revocation key settings')
            if self.apple_audiences:
                from cryptography.fernet import Fernet
                Fernet(self.apple_token_encryption_key.encode())
            if len(self.jwt_secret.encode()) < 32 or self.jwt_secret.startswith(("dev-", "change-me")):
                raise ValueError("Production requires a random JWT_SECRET of at least 32 bytes")
            if self.dev_login:
                raise ValueError("DEV_LOGIN must be disabled in production")
            if not self.cors_origins or any(not https_url(origin, origin=True) for origin in self.cors_origins):
                raise ValueError("Production CORS_ORIGINS must contain explicit HTTPS origins")


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]
