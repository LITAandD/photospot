"""Consent and public-share regression; onboarding runs only against localhost.
Pass --persist-test-events to verify test-tagged events through the production API.
No login/profile values or browser notes are sent. Physical devices are not tested.
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8798')
parser.add_argument('--persist-test-events', action='store_true')
parser.add_argument('--output', type=Path, default=Path('artifacts/release-1118'))
args = parser.parse_args()
assert urlparse(args.url).hostname in {'127.0.0.1', 'localhost'}
args.output.mkdir(parents=True, exist_ok=True)
DATE = '2026-11-22'
results = []
with sync_playwright() as pw:
    for engine, device, city in [('webkit', 'iPhone 13', 'gangneung'), ('chromium', 'Pixel 7', 'jeju'), ('chromium', None, 'gangneung')]:
        name = device or 'desktop'
        browser = getattr(pw, engine).launch()
        options = pw.devices[device] if device else {'viewport': {'width': 1280, 'height': 900}}
        context = browser.new_context(**options)
        page = context.new_page()
        events, stored, errors = [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def receive(route):
            body = route.request.post_data_json
            assert body['props']['traffic'] == 'test'
            assert body['props']['schema_version'] == 2
            assert '?' not in body['route']
            events.append(body)
            if args.persist_test_events:
                req = urllib.request.Request('https://photospot.litaandd.com/preview/events',
                    data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=30) as res:
                    assert res.status == 204
                    stored.append(body)
            route.fulfill(status=204, body='')
        context.route('**/preview/events', receive)
        context.add_init_script("""Object.defineProperty(navigator,'share',{value:undefined,configurable:true});
Object.defineProperty(navigator,'clipboard',{value:{writeText:async v=>{window.reviewShared=v}},configurable:true});""")
        visible = lambda loc: loc.locator('visible=true').last
        button = lambda label: visible(page.get_by_role('button', name=label, exact=True))
        page.goto(f'{args.url}/browse?city={city}&date={DATE}&traffic=test')
        cards = page.get_by_test_id('place-card').locator('visible=true')
        expect(cards).to_have_count(12, timeout=60000)
        place_name = cards.first.get_by_test_id('place-name').inner_text()
        cards.first.click()
        button('이 조건으로 맞춤 추천 설정').wait_for(timeout=30000)
        public_url = page.url
        place_id = urlparse(public_url).path.split('/')[-1]
        button('이 장소 공유하기').click()
        page.wait_for_function('!!window.reviewShared')
        shared = urlparse(page.evaluate('window.reviewShared').splitlines()[-1])
        assert shared.path == urlparse(public_url).path
        assert parse_qs(shared.query) == {'city':[city], 'date':[DATE], 'utm_source':['share']}
        fresh = browser.new_context(**options)
        fresh.route('**/preview/events', lambda route: (_ for _ in ()).throw(AssertionError('Consent absent')))
        fresh_page = fresh.new_page()
        fresh_page.goto(args.url + shared.path + '?' + shared.query)
        expect(fresh_page.get_by_role('heading', name=place_name, level=1)).to_be_visible(timeout=60000)
        expect(fresh_page.get_by_text(re.compile(DATE))).to_be_visible()
        fresh_page.screenshot(path=str(args.output / f'{engine}-{name}-public.png'), full_page=True)
        fresh.close()
        button('이 조건으로 맞춤 추천 설정').click()
        button('설정 중단하고 보던 장소로 돌아가기').click()
        button('이 조건으로 맞춤 추천 설정').wait_for(timeout=30000)
        assert place_id in page.url and city in page.url and DATE in page.url
        button('이 조건으로 맞춤 추천 설정').click()
        visible(page.get_by_role('checkbox', name='모두 동의', exact=True)).click()
        button('추천 시작하기').click()
        button('다음').click()
        button('다음').click()
        button('추천 받기').click()
        button('보던 장소 다시 보기').wait_for(timeout=60000)
        home_url = page.url
        assert city in home_url and DATE in home_url
        button('보던 장소 다시 보기').click()
        button('둘러보기 목록으로 돌아가기').wait_for(timeout=30000)
        assert place_id in page.url and city in page.url and DATE in page.url
        assert not events, 'No events before optional analytics opt-in'
        page.goto(args.url + '/settings?traffic=test')
        button('통계 공유 안 함 · 허용하기').click()
        expect(button('통계 공유 중 · 끄기')).to_be_visible()
        page.goto(home_url)
        expect(cards.first).to_be_visible(timeout=60000)
        cards.first.click()
        page.wait_for_timeout(700)
        names = {x['event'] for x in events}
        assert {'recommendation_request', 'place_view'} <= names, names
        page.goto(args.url + '/settings?traffic=test')
        button('통계 공유 중 · 끄기').click()
        expect(button('통계 공유 안 함 · 허용하기')).to_be_visible()
        before = len(events)
        assert page.evaluate("localStorage.getItem('photospot.analytics.choice.v2')") == 'deny'
        page.goto(home_url)
        expect(cards.first).to_be_visible(timeout=60000)
        cards.first.click()
        page.wait_for_timeout(700)
        assert len(events) == before, 'Events must stop after revocation'
        assert not errors, errors
        results.append(dict(engine=engine,device=name,physical=False,city=city,date=DATE,place_id=place_id,
                            share_context_preserved=True,customization_back_preserved=True,
                            before_consent=0,after_consent=len(events),after_revoke=0,
                            persisted=len(stored),sessions=sorted({x['session_id'] for x in stored}),
                            event_names=sorted(names),errors=errors))
        (args.output / 'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        print('PASS',engine,name,city,'events',len(events),'persisted',len(stored),flush=True)
        context.close()
        browser.close()
