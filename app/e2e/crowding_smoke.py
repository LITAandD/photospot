"""Local exported web bundle + opt-in Seoul public sample; no production traffic."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8774')
parser.add_argument('--output', type=Path, default=Path('artifacts/crowd-screens'))
parser.add_argument('--channel', default=None)
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}
args.output.mkdir(parents=True, exist_ok=True)
pid = '7f590a31-602f-5277-8534-ea1f7d86bc7c'
museum = 'bfcbd539-f1c5-5dff-97ad-a2fd0d8d8bec'
outside = 'c8d386f3-f380-5a32-9191-429b8e9d7320'
kst = timezone(timedelta(hours=9))
now = datetime.now(kst)
today, tomorrow = now.date().isoformat(), (now.date() + timedelta(days=1)).isoformat()


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=args.channel)
    for surface, width, height in [('desktop', 1100, 760), ('mobile', 390, 844)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=surface == 'mobile')
        page = context.new_page()
        events, errors = [], []
        page.on('request', lambda r: events.append(r.url) if '/preview/events' in r.url else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        obs = page.get_by_test_id('area-observation')
        forecast = page.get_by_test_id('visit-forecast')

        def open_place(place=pid, selected=today):
            page.goto(f'{args.url}/browse/{place}?city=seoul&date={selected}&traffic=test', wait_until='domcontentloaded')
            expect(page.get_by_role('button', name='이 조건으로 맞춤 추천 설정')).to_be_visible(timeout=30000)

        def shot(card, name):
            card.evaluate("(el) => el.scrollIntoView({block:'center'})")
            page.screenshot(path=args.output / f'{surface}-{name}.png', animations='disabled')

        for place in (pid, museum):
            open_place(place)
            expect(obs).to_contain_text('광화문·덕수궁 일대', timeout=12000)
            expect(forecast).to_have_count(0)
            if place == pid:
                shot(obs, 'observation')
        open_place(outside)
        assert page.request.get(f'{args.url}/preview/crowding/places/{outside}').json() == {'area': None, 'forecast': False}
        expect(obs).to_have_count(0)
        expect(forecast).to_have_count(0)

        # Only this local browser receives synthetic forecast values.
        source = {'area': 'POI009', 'forecast': True}
        page.route(f'**/crowding/places/{pid}', lambda route: route.fulfill(json=source))
        page.route('**/forecast', lambda route: route.fulfill(json=[{'date': today, 'index': 32}, {'date': tomorrow, 'index': 68}]))
        open_place()
        expect(obs).to_be_visible()
        expect(forecast).to_contain_text('덜 붐빌 전망')
        shot(forecast, 'both-fixture')
        open_place(selected=tomorrow)
        expect(forecast).to_contain_text('더 붐빌 전망')
        open_place(selected=(now + timedelta(days=2)).date().isoformat())
        expect(obs).to_be_visible()
        expect(forecast).to_have_count(0)

        source['area'] = None
        open_place()
        expect(forecast).to_be_visible()
        expect(obs).to_have_count(0)
        source['area'] = 'POI009'
        source['forecast'] = False
        # A valid badge disappears on its own when the returned observation expires.
        def expiring(route):
            t = datetime.now(kst)
            route.fulfill(json={'area_name': '광화문·덕수궁', 'level': '보통',
                                'observed_at': (t - timedelta(minutes=39, seconds=58)).isoformat(),
                                'expires_at': (t + timedelta(seconds=2)).isoformat()})
        page.route('**/crowding/areas/POI009', expiring)
        open_place()
        expect(obs).to_be_visible()
        expect(obs).to_have_count(0, timeout=6000)
        page.unroute('**/crowding/areas/POI009')
        for status in (200, 503):
            page.route('**/crowding/areas/POI009', lambda route: route.fulfill(status=status, content_type='application/json', body='null'))
            with page.expect_response(lambda r: '/crowding/areas/' in r.url):
                open_place()
            expect(obs).to_have_count(0)
            expect(forecast).to_have_count(0)
            expect(page.get_by_text('덕수궁', exact=True).first).to_be_visible()
            page.unroute('**/crowding/areas/POI009')
        # Same indicator on the personalized detail after local mandatory consent.
        page.unroute(f'**/crowding/places/{pid}')
        page.unroute('**/forecast')
        page.goto(args.url + '/login?traffic=test')
        page.get_by_role('checkbox', name='모두 동의', exact=True).click()
        page.get_by_role('button', name='추천 시작하기', exact=True).click()
        page.get_by_role('button', name='다음', exact=True).first.wait_for()
        page.goto(f'{args.url}/place/{pid}?date={today}&traffic=test')
        expect(obs).to_contain_text('광화문·덕수궁 일대', timeout=30000)
        expect(forecast).to_have_count(0)
        assert not events and not errors, (events, errors)
        print(surface, 'PASS live sample at two venues, unmatched, both / single / missing date, expiry, null, HTTP 503, personalized detail, no analytics', flush=True)
        context.close()
    browser.close()
