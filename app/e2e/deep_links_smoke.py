"""Route consent, diagnosis escape, fonts and permanent errors in the real web UI."""
from playwright.sync_api import sync_playwright, expect
import json
from pathlib import Path

BASE = 'http://localhost:8081'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(locale='ko-KR')
    context.add_init_script('''window.gpsCalls = 0;
      navigator.geolocation.getCurrentPosition = () => window.gpsCalls++;
      navigator.geolocation.watchPosition = () => { window.gpsCalls++; return 1; };''')
    page = context.new_page()
    page.set_default_timeout(20000)
    requests = []
    page.on('request', lambda r: requests.append(r.url) if '/preview/' in r.url else None)
    for path in ['/home', '/settings', '/saju']:
        page.goto(BASE + path)
        # Protected screens redirect to a public entry before any GPS/API effects.
        expect(page.get_by_text('체험용 로그인', exact=True)).to_be_visible()
        expect(page.get_by_role('checkbox')).not_to_be_checked()
        assert page.evaluate('window.gpsCalls') == 0
        assert not requests, requests
    page.get_by_role('checkbox').click()
    page.get_by_text('체험용 로그인', exact=True).click()
    expect(page.get_by_text('기본 정보를 알려주세요', exact=True)).to_be_visible()
    page.wait_for_function('''['IBMPlexSansKR_400Regular', 'GowunBatang_700Bold'].every(name =>
      Array.from(document.fonts).some(font => font.family.includes(name) && font.status === 'loaded'))''')
    # A new tab has no navigation history. Both close and applying a result must exit.
    direct = context.new_page()
    direct.set_default_timeout(20000)
    direct.goto(BASE + '/diagnosis/body-type')
    direct.get_by_role('button', name='닫기', exact=True).click()
    expect(direct).to_have_url(BASE + '/onboarding/style')
    direct.close()
    direct = context.new_page()
    direct.set_default_timeout(20000)
    direct.goto(BASE + '/diagnosis/body-type')
    questions = json.loads((Path(__file__).resolve().parents[1] / 'src/demo/diagnosis-questions.json').read_text(encoding='utf-8'))['body-type']
    for question in questions:
        expect(direct.get_by_text(question['text'], exact=True)).to_be_visible()
        direct.get_by_role('button', name=question['options'][0], exact=True).click()
    direct.get_by_text('이 결과로 입력하기', exact=True).click()
    expect(direct).to_have_url(BASE + '/onboarding/style')
    direct.goto(BASE + '/place/missing-place-id')
    expect(direct.get_by_text('장소를 찾을 수 없어요', exact=True)).to_be_visible()
    expect(direct.get_by_role('button', name='다시 시도', exact=True)).to_have_count(0)
    direct.get_by_role('button', name='추천 목록으로 돌아가기', exact=True).click()
    expect(direct.get_by_text('오늘 어디서 찍을까요', exact=True)).to_be_visible()
    direct.goto(BASE + '/does-not-exist')
    expect(direct.get_by_text('페이지를 찾을 수 없어요', exact=True)).to_be_visible()
    expect(direct.get_by_text('Sitemap', exact=False)).to_have_count(0)
    direct.goto(BASE + '/_sitemap')
    expect(direct.get_by_text('페이지를 찾을 수 없어요', exact=True)).to_be_visible()
    browser.close()
    print('PASS consent deep links, diagnosis exits, registered web fonts and permanent error pages')
