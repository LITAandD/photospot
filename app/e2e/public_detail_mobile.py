"""Local-only public detail layout regression; --live checks the real catalog/photo.

The fixed fixture is main's public response captured 2026-11-20 for 2026-11-23.
Synthetic variants and offline image pixels never reach the catalog or production.
"""
import argparse
import copy
from datetime import datetime, timezone
import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:8081')
parser.add_argument('--live', action='store_true')
parser.add_argument('--screenshots', default='artifacts/screenshots/public-detail')
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}, 'Local server only'
base = args.url.rstrip('/')
fixture = json.loads(Path(__file__).with_name('fixtures').joinpath('public-detail.json').read_text(encoding='utf8'))
place_id = fixture['place_id']
path = f'/browse/{place_id}?city=seoul&date=2026-11-23&traffic=test'
shots = Path(args.screenshots)
shots.mkdir(parents=True, exist_ok=True)
pixel = io.BytesIO()
Image.new('RGB', (300, 200), '#E2F7FD').save(pixel, format='PNG')


def isolate_ui_fixture(context, unexpected):
    # This test owns layout fixtures, not visitor-photo storage. Do not spend the
    # shared server's per-IP request budget before the other integration suites.
    def response(route):
        endpoint = urlparse(route.request.url).path
        if endpoint == '/preview/visitor-photos/policy':
            data = {'enabled': False, 'version': 'ui-test', 'operator': '', 'contact': '',
                    'policy_url': '/policies/visitor-photos.html', 'pending_days': 30,
                    'public_days': 365, 'max_file_bytes': 8_000_000}
        elif endpoint.startswith('/preview/visitor-photos/places/'):
            data = {'enabled': False, 'items': []}
        else:
            unexpected.append(endpoint)
            route.abort()
            return
        route.fulfill(json=data, headers={'Access-Control-Allow-Origin': '*'})
    context.route('**/preview/**', response)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for width, height in [(360, 740), (390, 844), (1280, 900)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, locale='ko-KR')
        unexpected = []
        if not args.live:
            isolate_ui_fixture(context, unexpected)
        context.grant_permissions(['clipboard-read', 'clipboard-write'])
        context.add_init_script("Object.defineProperty(navigator, 'share', {value: undefined, configurable: true})")
        if not args.live:
            context.route('https://*.wikimedia.org/**', lambda route: route.fulfill(content_type='image/png', body=pixel.getvalue()))
        page = context.new_page()
        page.clock.set_fixed_time(datetime(2026, 11, 20, 3, tzinfo=timezone.utc))
        events, errors = [], []
        page.on('request', lambda r: events.append(r.url) if '/preview/events' in r.url else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        current = None if args.live else fixture

        def detail_response(route):
            if current is None:
                route.continue_()
            else:
                route.fulfill(json=current, headers={'Access-Control-Allow-Origin': '*'})

        page.route(f'**/preview/browse/{place_id}?*', detail_response)

        def open_detail(visit_date='2026-11-23'):
            page.goto(base + path.replace('2026-11-23', visit_date))
            expect(page.get_by_test_id('public-visit-info')).to_be_visible(timeout=60000)
            page.evaluate('document.fonts.ready')

        def footer():
            bar = page.get_by_test_id('public-place-actions')
            expect(bar.get_by_role('button')).to_have_count(2)
            for label in ['이 장소 공유하기', '네이버 지도 열기']:
                button = bar.get_by_role('button', name=label)
                bounds = button.bounding_box()
                assert bounds and bounds['width'] >= 44 and bounds['height'] >= 44
            bounds = bar.bounding_box()
            if width < 680:
                assert bounds and 0 <= bounds['y'] and bounds['y'] + bounds['height'] <= height + 1, bounds
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Horizontal overflow'
            return bounds

        open_detail()
        info = page.get_by_test_id('public-visit-info')
        expect(info.get_by_text('선택한 날짜 · 2026-11-23', exact=True)).to_be_visible()
        expect(info.get_by_text('09:00–17:00', exact=True)).to_be_visible()
        expect(info.get_by_text('입장 마감 16:00', exact=True)).to_be_visible()
        image = page.get_by_test_id('place-photo-image').first
        page.wait_for_function("Array.from(document.querySelectorAll('[data-testid=place-photo-image]')).some(i => i.complete && i.naturalWidth > 0)", timeout=60000)
        image.evaluate('(i) => i.decode()')
        ratio = image.evaluate('(i) => ({actual:i.width/i.height, original:i.naturalWidth/i.naturalHeight})')
        assert abs(ratio['actual'] - ratio['original']) < .02, ratio
        assert page.get_by_role('heading', level=1).bounding_box()['y'] < image.bounding_box()['y'] < info.bounding_box()['y']
        assert page.get_by_text(fixture['address'], exact=True).bounding_box()['y'] < image.bounding_box()['y']
        expect(page.get_by_role('link', name='사진 출처', exact=True)).to_be_visible()
        expect(page.get_by_role('link', name='사진 이용 조건', exact=True)).to_be_visible()
        first_footer = footer()
        if width < 680:
            # The date, clock and fee lead are visible without scrolling on both target widths.
            fee = info.get_by_text('일반 관람료 · 대인 개인 3,000원', exact=True).bounding_box()
            assert fee['y'] + fee['height'] <= first_footer['y'], (width, fee, first_footer)
        page.screenshot(path=str(shots / f'after-{width}.png'))
        info.get_by_role('button', name='요금 조건·출처·확인일 ＋').click()
        expect(info.get_by_text(fixture['facts'][1]['value'], exact=True)).to_be_visible()
        expect(info.get_by_role('link', name='궁능유적본부 공식 관람 안내 · 2026-11-12 확인 ↗')).to_be_visible()
        info.get_by_role('button', name='방문 정보 접기 −').click()
        page.get_by_role('button', name='사진 안내 ＋', exact=True).click()
        expect(page.get_by_role('link', name='원본 사진', exact=True)).to_be_visible()
        page.get_by_role('button', name='사진 안내 접기 −', exact=True).click()
        expect(page.get_by_role('link', name='공식 관람코스 보기 ↗')).to_be_visible()
        page.get_by_role('button', name='상세 방문 안내', exact=True).click()
        expect(page.get_by_test_id('place-hours')).to_be_visible()
        page.get_by_role('button', name='이 조건으로 맞춤 추천 설정').scroll_into_view_if_needed()
        end_button = page.get_by_role('button', name='이 조건으로 맞춤 추천 설정').bounding_box()
        bottom = footer()
        if width < 680:
            assert abs(first_footer['y'] - bottom['y']) <= 1
            assert end_button['y'] + end_button['height'] <= bottom['y'] + 1, 'Footer obscures last action'
        page.get_by_role('button', name='이 장소 공유하기', exact=True).click()
        expect(page.get_by_text(re.compile('링크와 내용을 복사했어요'))).to_be_visible()
        shared = urlparse(page.evaluate('navigator.clipboard.readText()').strip().splitlines()[-1])
        assert shared.path == f'/browse/{place_id}'
        assert parse_qs(shared.query) == {'city': ['seoul'], 'date': ['2026-11-23'], 'utm_source': ['share']}
        fresh = browser.new_context(viewport={'width': width, 'height': height})
        if not args.live:
            isolate_ui_fixture(fresh, unexpected)
        fresh_page = fresh.new_page()
        fresh_page.clock.set_fixed_time(datetime(2026, 11, 20, 3, tzinfo=timezone.utc))
        fresh_page.route(f'**/preview/browse/{place_id}?*', lambda route: route.fulfill(json=fixture, headers={'Access-Control-Allow-Origin': '*'}))
        fresh_page.goto(f'{base}{shared.path}?{shared.query}')
        expect(fresh_page.get_by_role('heading', name='경복궁', exact=True)).to_be_visible(timeout=60000)
        expect(fresh_page.get_by_text('선택한 날짜 · 2026-11-23', exact=True)).to_be_visible()
        assert fresh_page.evaluate('localStorage.getItem("photospot.profile")') is None
        fresh.close()
        page.evaluate("window.__map = ''; window.open = (url) => { window.__map = url; return null }")
        page.get_by_role('button', name='네이버 지도 열기', exact=True).click()
        assert 'map.naver.com' in page.evaluate('window.__map')

        # Keep the same API contract; these scenarios are UI fixtures, not new place data.
        for variant in ['long-name', 'no-photo', 'closed', 'unknown', 'stale']:
            current = copy.deepcopy(fixture)
            if variant == 'long-name':
                current['name'] = '아주 긴 장소명으로 줄바꿈을 확인하는 문화예술 복합시설 별관 전시관'
            elif variant == 'no-photo':
                current['cover_photo'] = None
            elif variant == 'closed':
                current['hours'].update(closed=True, summary='화 정기휴궁 (정규)')
                if args.live:
                    current = context.request.get(f'{base}/preview/browse/{place_id}?city=seoul&visit_date=2026-11-24').json()
                    assert current['hours']['closed'], 'Real catalog must identify the selected Tuesday closure'
            elif variant == 'unknown':
                current.update(hours=None, cover_photo=None, facts=[])
            else:
                current['hours'].update(stale=True, summary='공식 안내 확인 (게시 기간 만료)')
            open_detail('2026-11-24' if variant == 'closed' else '2026-11-23')
            footer()
            if current['cover_photo']:
                page.wait_for_function("Array.from(document.querySelectorAll('[data-testid=place-photo-image]')).some(i => i.complete && i.naturalWidth > 0)", timeout=60000)
                page.get_by_test_id('place-photo-image').first.evaluate('(i) => i.decode()')
            if variant in {'no-photo', 'unknown'}:
                expect(page.get_by_text('사진 준비 중', exact=True)).to_be_visible()
                expect(page.get_by_test_id('place-photo-image')).to_have_count(0)
            if variant == 'closed':
                expect(info.get_by_text('선택일 휴관·휴무', exact=True)).to_be_visible()
            if variant in {'unknown', 'stale'}:
                expect(info.get_by_text('운영시간 확인 필요', exact=True)).to_be_visible()
            if variant == 'unknown':
                expect(info.get_by_text('관람료 · 확인 필요', exact=True)).to_be_visible()
            if variant in {'closed', 'unknown', 'stale'}:
                expect(info.get_by_text('입장 마감 16:00', exact=True)).to_have_count(0)
            page.screenshot(path=str(shots / f'{variant}-{width}.png'))
        assert not events, 'No analytics before consent, including test traffic'
        assert not errors, errors
        assert not unexpected, f'UI fixture made an unmocked API call: {unexpected}'
        print(f'PASS {width}: natural photo, first-fold visit data, sources, fixed actions, fresh share, map, five variants, no analytics', flush=True)
        context.close()
    browser.close()
