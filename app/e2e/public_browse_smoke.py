"""Local-only public browse regression. Fresh profiles; analytics remain off."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:8081')
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}, 'Never run onboarding tests against production'
base = args.url.rstrip('/')
shots = Path('artifacts/public-browse')
shots.mkdir(parents=True, exist_ok=True)
future = (datetime.now(timezone(timedelta(hours=9))) + timedelta(days=7)).date().isoformat()

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for name, viewport in [('mobile', {'width': 390, 'height': 844}), ('desktop', {'width': 1280, 'height': 900})]:
        context = browser.new_context(viewport=viewport, is_mobile=name == 'mobile', has_touch=name == 'mobile')
        page = context.new_page()
        events, errors = [], []
        page.on('request', lambda r: events.append(r.url) if r.url.endswith('/preview/events') else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        visible = lambda locator: locator.locator('visible=true').last
        button = lambda label: visible(page.get_by_role('button', name=label, exact=True))
        def cards():
            return page.get_by_test_id('place-card').locator('visible=true')
        def choose_city(label):
            # RN Web exposes a button with aria-pressed (AX may announce it as checkbox).
            visible(page.get_by_text(label, exact=True)).click()
        def wait_cards():
            cards().first.wait_for(timeout=60000)
        page.goto(base + '/browse?traffic=test', wait_until='domcontentloaded')
        expect(visible(page.get_by_text('먼저 둘러볼 도시를 선택해 주세요.', exact=True))).to_be_visible(timeout=60000)
        expect(cards()).to_have_count(0)
        choose_city('서울')
        wait_cards()
        for forbidden in ['recommendation-reason', 'recommendation-evidence']:
            expect(cards().get_by_test_id(forbidden)).to_have_count(0)
        assert '산정 전' not in cards().first.inner_text()
        assert '서울 종로·북촌 기준' in cards().first.inner_text()
        # A date chosen from the actual calendar persists in route and public detail.
        button('촬영일 달력 열기').click()
        year, month = map(int, future[:7].split('-'))
        y, m = map(int, re.findall(r'\d+', visible(page.get_by_test_id('calendar-month')).inner_text()))
        for _ in range((year - y) * 12 + month - m):
            button('다음 달').click()
        visible(page.get_by_test_id('calendar-day-' + future)).click()
        wait_cards()
        assert parse_qs(urlparse(page.url).query)['date'] == [future]
        first_name = cards().first.get_by_test_id('place-name').inner_text()
        cards().first.click()
        button('둘러보기 목록으로 돌아가기').wait_for()
        button('이 조건으로 맞춤 추천 설정').wait_for(timeout=60000)
        detail_url = page.url
        assert '/browse/' in detail_url and 'city=seoul' in detail_url and future in detail_url
        expect(visible(page.get_by_text(first_name, exact=True))).to_be_visible()
        if visible(page.get_by_test_id('photo-credit')).count():
            expect(visible(page.get_by_test_id('photo-credit'))).to_be_visible()
        page.reload()
        button('이 조건으로 맞춤 추천 설정').wait_for(timeout=60000)
        page.screenshot(path=str(shots / f'{name}-detail.png'), full_page=True)
        button('둘러보기 목록으로 돌아가기').click()
        wait_cards()
        assert future in page.url and 'city=seoul' in page.url
        cards().first.click()
        button('이 조건으로 맞춤 추천 설정').click()
        button('추천 시작하기').wait_for()
        expect(button('추천 시작하기')).to_be_disabled()
        button('설정 중단하고 보던 장소로 돌아가기').click()
        button('이 조건으로 맞춤 추천 설정').wait_for(timeout=60000)
        assert future in page.url and '/browse/' in page.url
        # Local mock consent flow only: no external terms/account creation.
        button('이 조건으로 맞춤 추천 설정').click()
        visible(page.get_by_role('checkbox', name='모두 동의', exact=True)).click()
        button('추천 시작하기').click()
        button('다음').click()
        button('다음').click()
        button('추천 받기').click()
        button('보던 장소 다시 보기').wait_for(timeout=60000)
        assert '/home?' in page.url and f'date={future}' in page.url and 'city=seoul' in page.url
        expect(visible(page.get_by_text('서울 종로·북촌', exact=True))).to_be_visible()
        button('보던 장소 다시 보기').click()
        button('둘러보기 목록으로 돌아가기').wait_for()
        button('둘러보기 목록으로 돌아가기').click()
        wait_cards()
        # City change must reset the list; CI fixture may have no Busan records.
        choose_city('부산')
        page.wait_for_url(re.compile(r'city=busan'))
        expect(visible(page.get_by_role('progressbar'))).to_have_count(0, timeout=60000)
        if cards().count():
            assert '부산 해운대·미포 기준' in cards().first.inner_text()
        else:
            expect(visible(page.get_by_text('선택한 기준점 주변 5km에 공개할 장소 정보가 아직 없어요.', exact=True))).to_be_visible()
        choose_city('서울')
        wait_cards()
        page.screenshot(path=str(shots / f'{name}-cards.png'), full_page=True)
        # Missing detail is recoverable via the list, not an endless retry.
        page.goto(base + '/browse/00000000-0000-0000-0000-000000000000?city=seoul&date=' + future)
        expect(visible(page.get_by_text('이 장소를 찾을 수 없어요.', exact=True))).to_be_visible(timeout=60000)
        expect(button('다시 시도')).to_have_count(0)
        assert not events, 'Default-off analytics must not send any event'
        assert not errors, errors
        print(f'PASS {name}: public cards/detail, calendar, city, reload/back, cancel/finish customization, missing place, analytics off', flush=True)
        context.close()
    browser.close()
