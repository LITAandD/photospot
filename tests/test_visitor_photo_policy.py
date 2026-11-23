from pathlib import Path

from deploy.vercel.frontend import PUBLIC_ROUTES

ROOT = Path(__file__).resolve().parents[1]


def test_visitor_policy_is_in_build_and_sitemap():
    assert PUBLIC_ROUTES.count('/policies/visitor-photos.html') == 1
    build = (ROOT / 'scripts/build-web-preview.cjs').read_text(encoding='utf-8')
    assert "EXPO_PUBLIC_VISITOR_PHOTOS_URL: 'visitor-photos'" in build
    assert "'account-deletion', 'visitor-photos'" in build


def test_privacy_and_deletion_describe_actual_server_storage():
    privacy = (ROOT / 'app/public/policies/privacy.html').read_text(encoding='utf-8')
    deletion = (ROOT / 'app/public/policies/account-deletion.html').read_text(encoding='utf-8')
    assert 'LIT A&amp;D' in privacy and 'info@litaandd.com' in privacy
    for text in ['사용자 촬영 예시(웹·선택)', '얼굴 가림 영역', 'IP 일별 가명값', '최대 365일', '관리 코드로 철회', '본인이 별도로 확인']:
        assert text in privacy
    assert '브라우저 데이터 삭제로 지워지지 않습니다' in deletion
    assert 'info@litaandd.com' in deletion
