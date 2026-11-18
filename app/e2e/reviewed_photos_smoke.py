"""Verify the five reviewed covers against the locally built app and its catalog copy."""
import argparse
from datetime import date
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8794')
parser.add_argument('--channel', default=None)
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}
out = ROOT / 'artifacts/photo-qa'
out.mkdir(parents=True, exist_ok=True)
commons = json.loads((ROOT / 'deploy/data/reviewed_place_photos_20261113.json').read_text('utf8'))
tourism = json.loads((ROOT / 'deploy/data/reviewed_tourism_photos.json').read_text('utf8'))
rows = [(r['place_id'], r['file_title'], r['url'], r['attribution'], 'commons') for r in commons]
rows += [(r['place']['id'], r['place']['name'], r['photo']['url'], r['photo']['credit'], 'kor') for r in tourism]
results, listings = [], []
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=args.channel)
    for width, height in [(390, 844), (1365, 900)]:
        ctx = browser.new_context(viewport={'width': width, 'height': height}, locale='ko-KR', has_touch=width == 390)
        page = ctx.new_page()
        events = []
        page.on('request', lambda r: events.append(r.url) if '/preview/events' in r.url else None)
        for city in ('seoul', 'busan', 'gangneung', 'jeju'):
            page.goto(f'{args.url}/browse?city={city}&date=2026-11-16&traffic=test', wait_until='domcontentloaded')
            cards = page.get_by_test_id('place-card').locator('visible=true')
            expect(cards).to_have_count(12, timeout=30000)
            decoded = 0
            for card in cards.all():
                card.scroll_into_view_if_needed()
                image = card.get_by_test_id('place-photo-image')
                if image.count():
                    try:
                        page.wait_for_function('(card) => {const i=card.querySelector("img");return i?.complete && i.naturalWidth>0}', arg=card.element_handle(), timeout=8000)
                        decoded += 1
                    except PlaywrightTimeoutError:
                        pass  # A broken external image counts in the denominator only.
            listings.append({'width': width, 'city': city, 'cards': 12, 'decoded': decoded})
            print(listings[-1], flush=True)
        # Some reviewed sites lie beyond public browse's 5 km. Use the existing consented detail route.
        page.goto(args.url + '/login?traffic=test')
        page.get_by_role('checkbox', name='모두 동의', exact=True).click()
        page.get_by_role('button', name='추천 시작하기', exact=True).click()
        page.get_by_role('button', name='다음', exact=True).first.wait_for()
        for pid, name, url, credit, source in rows:
            start = time.perf_counter()
            page.goto(f'{args.url}/place/{pid}?date={date.today().isoformat()}&traffic=test', wait_until='domcontentloaded')
            picture = page.get_by_test_id('pose-place-photo').last
            expect(picture).to_be_visible(timeout=30000)
            decoded_width = page.wait_for_function('''(url) => [...document.querySelectorAll('[data-testid=pose-place-photo] img, img[data-testid=pose-place-photo]')].find(i=>i.getAttribute('src')===url && i.complete && i.naturalWidth>0)?.naturalWidth''', arg=url, timeout=20000).json_value()
            caption = page.get_by_test_id('photo-credit').filter(has_text=credit).first
            expect(caption).to_contain_text('1', timeout=10000)
            for label in ('사진 출처', '사진 이용 조건', '원본 사진'):
                expect(caption.get_by_role('link', name=label, exact=True)).to_be_visible()
            caption.scroll_into_view_if_needed()
            page.screenshot(path=out / f'{width}-{pid}.png')
            record = dict(width=width, place_id=pid, name=name, source=source, natural_width=decoded_width,
                          seconds=round(time.perf_counter()-start, 2))
            results.append(record)
            print(record, flush=True)
        assert not events
        ctx.close()
    browser.close()
(out / 'result.json').write_text(json.dumps(dict(details=results, first_page=listings), ensure_ascii=False, indent=2), 'utf8')
