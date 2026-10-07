"""Pure deployment checks; messages never contain configuration values."""
import ipaddress
from urllib.parse import urlsplit


def https_url(value: str, *, origin: bool = False, public: bool = False) -> bool:
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower().rstrip('.')
        if (url.scheme != 'https' or not host or url.username is not None or url.password is not None
                or '*' in host or url.fragment or any(c.isspace() for c in value)):
            return False
        _ = url.port  # Reject invalid ports as well as malformed hosts.
        if origin and (url.path not in ('', '/') or url.query):
            return False
        if public:
            try:
                ipaddress.ip_address(host)
                return False  # Deployment endpoints must use DNS names.
            except ValueError:
                pass
            if '.' not in host or host.split('.')[-1] in {'localhost', 'local', 'internal', 'test', 'invalid', 'example'}:
                return False
            if any(host == h or host.endswith('.' + h) for h in ('example.com', 'example.org', 'example.net')):
                return False
        return True
    except (ValueError, TypeError):
        return False


def server_issues(env, *, growth=False):
    issues = []
    if env.get('APP_ENV') != 'production':
        issues.append('APP_ENV: production으로 설정하세요')
    secret = env.get('JWT_SECRET', '')
    if len(secret.encode()) < 32 or secret.startswith(('dev-', 'change-me')):
        issues.append('JWT_SECRET: 32바이트 이상의 무작위 비밀키가 필요해요')
    if env.get('DEV_LOGIN') != '0':
        issues.append('DEV_LOGIN: 0으로 설정하세요')
    dsn = env.get('DATABASE_URL', '')
    try:
        db = urlsplit(dsn)
        valid_db = db.scheme in {'postgres', 'postgresql'} and db.hostname and db.path not in ('', '/')
        _ = db.port
    except ValueError:
        valid_db = False
    if not valid_db:
        issues.append('DATABASE_URL: 운영 PostgreSQL 접속 주소를 설정하세요')
    elif db.password in {'photospot', 'postgres', 'password', 'changeme'}:
        issues.append('DATABASE_URL: 개발용 기본 암호를 운영에서 사용할 수 없어요')
    origins = [item.strip() for item in env.get('CORS_ORIGINS', '').split(',') if item.strip()]
    if not origins or any(not https_url(item, origin=True, public=True) for item in origins):
        issues.append('CORS_ORIGINS: 실제 공개 HTTPS origin만 허용하세요 (경로·와일드카드 제외)')
    if not (env.get('GOOGLE_CLIENT_IDS') or env.get('KAKAO_APP_ID') or env.get('NAVER_LOGIN_ENABLED') == '1'):
        issues.append('Android 로그인: 서버에서 Google·카카오·네이버 중 하나 이상 설정하세요')
    # Both mobile platforms are in scope; Apple revocation requires the full key set.
    for key in ('APPLE_AUDIENCES', 'APPLE_CLIENT_ID', 'APPLE_TEAM_ID', 'APPLE_KEY_ID', 'APPLE_PRIVATE_KEY_PATH', 'APPLE_TOKEN_ENCRYPTION_KEY'):
        if not env.get(key):
            issues.append(f'{key}: Apple 로그인·연결 해제·탈퇴 설정이 필요해요')
    if env.get('APPLE_CLIENT_ID') and env.get('APPLE_CLIENT_ID') not in [v.strip() for v in env.get('APPLE_AUDIENCES', '').split(',')]:
        issues.append('APPLE_CLIENT_ID: 서버 APPLE_AUDIENCES와 일치해야 해요')
    if env.get('APPLE_TOKEN_ENCRYPTION_KEY'):
        from cryptography.fernet import Fernet
        try:
            Fernet(env['APPLE_TOKEN_ENCRYPTION_KEY'].encode())
        except (ValueError, TypeError):
            issues.append('APPLE_TOKEN_ENCRYPTION_KEY: 유효한 Fernet 키가 필요해요')
    if growth or env.get('INSTAGRAM_CLIENT_ID'):
        for key in ('INSTAGRAM_CLIENT_ID', 'INSTAGRAM_CLIENT_SECRET'):
            if not env.get(key):
                issues.append(f'{key}: Instagram 서버 설정이 필요해요')
        redirect = env.get('INSTAGRAM_REDIRECT_URI', '')
        if (not https_url(redirect, public=True) or urlsplit(redirect).path != '/v1/social/instagram/callback'
                or urlsplit(redirect).query):
            issues.append('INSTAGRAM_REDIRECT_URI: 공개 HTTPS API의 /v1/social/instagram/callback 주소를 설정하세요')
    if growth:
        for key in ('REVENUECAT_SECRET_KEY', 'OPENAI_API_KEY'):
            if not env.get(key):
                issues.append(f'{key}: 서버 비밀 저장소에 설정하세요')
    return issues
