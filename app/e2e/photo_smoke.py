"""Verify real photo links and gallery UI; --offline-images substitutes pixels in CI only."""
import argparse
import base64
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')
from pipeline.place_catalog import connect

parser = argparse.ArgumentParser()
parser.add_argument('--channel', default=None)
parser.add_argument('--offline-images', action='store_true')
args = parser.parse_args()
shots = ROOT / 'artifacts' / 'screenshots'
shots.mkdir(parents=True, exist_ok=True)
with connect() as conn:
    candidate = conn.execute('''SELECT p.id,p.name,count(*) n FROM places p JOIN catalog_photos cp ON cp.place_id=p.id
        WHERE p.active=1 AND p.lat BETWEEN 37.54 AND 37.61 AND p.lng BETWEEN 126.95 AND 127.02
        GROUP BY p.id HAVING count(*)>=2 ORDER BY count(*) DESC,p.id LIMIT 1''').fetchone()
    assert candidate, 'Import the real public photo metadata fixture or live photo catalog first'

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=args.channel, headless=True)
    context = browser.new_context(viewport={'width':390,'height':844}, locale='ko-KR',
                                  geolocation={'latitude': 37.5796, 'longitude': 126.977}, permissions=['geolocation'])
    if args.offline_images:
        # Test-only raster response: never written to the catalog or served to the user.
        pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=')
        context.route('https://*.wikimedia.org/**', lambda route: route.fulfill(status=200,content_type='image/png',body=pixel))
    page = context.new_page()
    page.set_default_timeout(20000)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    visible = lambda locator: locator.locator('visible=true').last
    click = lambda label: visible(page.get_by_text(label, exact=True)).click()
    try:
        page.goto('http://localhost:8081', wait_until='domcontentloaded')
        click('시작하기')
        visible(page.get_by_role('checkbox')).click()
        click('체험용 로그인')
        click('다음')
        click('웨이브')
        click('다음')
        click('추천 받기')
        click('추천 장소 보기')
        page.goto('http://localhost:8081/place/' + candidate['id'] + '?date=2026-10-10')
        gallery = visible(page.get_by_test_id('place-gallery'))
        expect(gallery).to_contain_text(f"장소 사진 · {candidate['n']}장")
        first = gallery.get_by_test_id('place-photo-image').first
        expect(first).to_be_visible()
        # RN Web can render an image as a wrapper containing img; inspect rendered pixels.
        def loaded(locator):
            page.wait_for_function('''node => {
                const img = node instanceof HTMLImageElement ? node : node.querySelector('img');
                return img && img.complete && img.naturalWidth > 0;
            }''', arg=locator.element_handle(), timeout=60000)
        def image_url(locator):
            return locator.evaluate("node => (node instanceof HTMLImageElement ? node : node.querySelector('img')).src")
        loaded(first)
        first_url = image_url(first)
        gallery.scroll_into_view_if_needed()
        expect(gallery.get_by_test_id('photo-credit')).to_contain_text('사진 이용 조건')
        before = gallery.get_by_test_id('photo-credit').inner_text()
        click('다음 사진')
        expect(gallery).to_contain_text(f"2 / {candidate['n']}")
        loaded(first)
        assert image_url(first) != first_url, 'Next must show a different photo'
        assert before and gallery.get_by_test_id('photo-credit').inner_text()
        click('이전 사진')
        expect(gallery).to_contain_text(f"1 / {candidate['n']}")
        page.screenshot(path=str(shots / ('09_photo_gallery_offline.png' if args.offline_images else '09_photo_gallery.png')))
        click('저장 ♡')
        visible(page.get_by_text('저장됨 ♥', exact=True)).wait_for()
        page.goto('http://localhost:8081/saved')
        expect(visible(page.get_by_text(candidate['name'], exact=True))).to_be_visible()
        expect(visible(page.get_by_test_id('place-photo-image'))).to_be_visible()
        loaded(visible(page.get_by_test_id('place-photo-image')))
        assert not errors, errors
        print(f"PASS photo gallery, attribution, previous/next, saved cover; {candidate['name']} ({candidate['n']} photos)")
    finally:
        browser.close()
