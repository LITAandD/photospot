"""Local-only synthetic profiles: evidence coverage vs fit, no analytics writes."""
import argparse
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:8081')
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}
shots = Path('artifacts/evidence-ui')
shots.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for name, width, height in [('mobile', 390, 844), ('desktop', 1280, 900)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=name == 'mobile', has_touch=name == 'mobile')
        page = context.new_page()
        page.set_default_timeout(60000)
        events, errors, results = [], [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: events.append(r.url) if r.url.endswith('/preview/events') else None)
        page.on('response', lambda r: results.append(r.json()) if r.url.endswith('/preview/evaluate') and r.status == 200 else None)
        visible = lambda locator: locator.locator('visible=true').last
        click = lambda text: visible(page.get_by_text(text, exact=True)).click()
        page.goto(args.url + '/login?traffic=test', wait_until='domcontentloaded')
        visible(page.get_by_role('checkbox', name='모두 동의', exact=True)).click()
        click('추천 시작하기')
        click('다음')
        click('봄 웜')
        click('웨이브')
        click('다음')
        for letter in ['E', 'N', 'F', 'J']: click(letter)
        click('추천 받기')
        click('추천 장소 보기')
        cards = page.get_by_test_id('place-card').locator('visible=true')
        cards.first.wait_for()
        assert cards.count() > 0 and results
        scores = [r['fit_score'] if r['fit_score'] is not None else -1 for r in results[-1]['recommendations']['items']]
        assert scores == sorted(scores, reverse=True)
        # Fit is primary, so a category-only venue can correctly rank first.
        # Require an analyzed photo, then inspect that actual card; do not pass
        # with zero results or silently skip the photo-brightness assertion.
        analyzed = [i for i, item in enumerate(results[-1]['recommendations']['items'])
                    if any(m['key'] == 'pc_tone.brightness' and m['status'] == 'scored'
                           for m in item['scoring']['metrics'])]
        assert analyzed, 'Fixture must contain at least one evaluated photo-brightness metric'
        cards.nth(analyzed[0]).click()
        coverage = visible(page.get_by_test_id('score-evidence-coverage'))
        expect(coverage).to_contain_text('근거 확보')
        method = visible(page.get_by_test_id('score-method'))
        method.get_by_role('button').click()
        expect(visible(page.get_by_test_id('score-preference-fit'))).to_contain_text('전체 정합도나 추천 순서와는 달라요')
        brightness = visible(page.get_by_test_id('score-metric-pc_tone.brightness'))
        brightness.get_by_role('button').click()
        expect(brightness).to_contain_text('현장 조도 실측값이 아니에요')
        visible(page.get_by_test_id('score-details')).scroll_into_view_if_needed()
        page.screenshot(path=str(shots/f'{name}-evidence.png'), full_page=True)
        assert not errors, errors
        assert not events, 'Analytics must remain off even after required consent'
        print(f'PASS {name}: nonempty sorted recommendations, separate coverage/fit, photo brightness, analytics off', flush=True)
        context.close()
    browser.close()
