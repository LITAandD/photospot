"""Verify real photo links and gallery UI; --offline-images substitutes pixels in CI only."""
import argparse
import base64
from pathlib import Path
import re
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
    instagram_requests = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text)
            if message.type == 'error' and 'Encountered two children with the same key' in message.text else None)
    page.on('request', lambda request: instagram_requests.append(request.url) if 'instagram.com' in request.url else None)
    # Exercise a licensed gallery that also has an old Instagram reference.
    # This mutates only the local CI response, never the shipped catalog.
    fallback_only = False
    # Isolated browser contract for writes; PostgreSQL/cookie behavior is covered
    # by test_photo_likes.py against a real database. Never writes production votes.
    browser_votes = {}
    def like_response(route):
        if route.request.url.endswith('/session'):
            return route.fulfill(json={'ok': True})
        body = route.request.post_data_json
        browser_votes[body['photo_id']] = int(body['liked'])
        route.fulfill(json={'photo_id': body['photo_id'], 'liked': body['liked'],
                            'like_count': browser_votes[body['photo_id']]})
    page.route('**/preview/photo-likes/*', like_response)
    def with_legacy_post(route):
        response = route.fetch()
        data = response.json()
        detail = data.get('places', {}).get(candidate['id'])
        if detail:
            for photo in detail['photos']:
                photo.update(likes_enabled=True, like_count=browser_votes.get(photo['photo_id'], 0),
                             liked=bool(browser_votes.get(photo['photo_id'], 0)))
            detail['photos'].sort(key=lambda p: -p['like_count'])
            detail['instagram_posts'] = [{'permalink': 'https://www.instagram.com/p/CTdZy30Bu4u/',
                                         'label': '원본 게시물 확인', 'checked_at': '2026-10-13'}]
            if fallback_only:
                detail['photos'] = []
        route.fulfill(response=response, json=data)
    page.route('**/preview/evaluate', with_legacy_post)
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
        expect(page.locator('iframe[src*="instagram.com"]')).to_have_count(0)
        expect(page.get_by_test_id('place-photo-source-links')).to_have_count(0)
        guide = visible(page.get_by_test_id('place-pose-guide'))
        guide.scroll_into_view_if_needed()
        pose = guide.get_by_test_id('chalk-pose')
        expect(pose).to_be_visible()
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('사진 속 인물 기준')
        original = pose.bounding_box()
        guide.get_by_role('button', name='포즈 스케치 작게', exact=True).click()
        assert pose.bounding_box()['height'] < original['height']
        guide.get_by_role('button', name='포즈 스케치 크기 초기화', exact=True).click()
        assert abs(pose.bounding_box()['height'] - original['height']) < 1
        guide.get_by_role('button', name='사진 속 사람 크기에 맞추기', exact=True).click()
        measure = guide.get_by_test_id('pose-measure-surface')
        bounds = measure.bounding_box()
        measure.click(position={'x': bounds['width'] * 0.6, 'y': bounds['height'] * 0.4})
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('발끝')
        measure.click(position={'x': bounds['width'] * 0.6, 'y': bounds['height'] * 0.7})
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('선택한 인물 기준')
        calibrated = pose.bounding_box()
        guide.get_by_role('button', name='움직임 포즈 모음', exact=True).click()
        guide.get_by_role('button', name='한 걸음 포즈', exact=True).click()
        step = pose.bounding_box()
        # Different pose paths have slightly different SVG padding but share the visible body height/ground.
        assert abs(calibrated['height'] * 148 / 176 - step['height'] * 145 / 176) < 1
        guide.get_by_role('button', name='포즈 스케치 크기 초기화', exact=True).click()
        page.screenshot(path=str(shots / '10_pose_person_scale.png'))
        # The same calibration must be possible without pointing at image pixels.
        guide.get_by_role('button', name='사진 속 사람 크기에 맞추기', exact=True).press('Enter')
        guide.get_by_label('인물 머리 위치 (%)', exact=True).fill('30')
        guide.get_by_label('인물 발끝 위치 (%)', exact=True).fill('70')
        guide.get_by_role('button', name='입력한 인물 크기 적용', exact=True).press('Enter')
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('선택한 인물 기준 · 사진 높이의 40%')
        # Every pose is reachable, visibly distinct, and preserves the calibrated stature.
        guide.get_by_role('button', name='스케치 오른쪽 배치', exact=True).press('Enter')
        silhouettes = set()
        for group, labels in [
            ('서 있기', ['자연스럽게', '옆모습', '뒤돌아보기', '다리 교차']),
            ('움직임', ['한 걸음', '팔 벌리기', '손 흔들기', '머리 넘기기']),
            ('앉기', ['걸터앉기', '옆으로 앉기', '바닥에 앉기', '쪼그려 앉기']),
        ]:
            guide.get_by_role('button', name=f'{group} 포즈 모음', exact=True).press('Enter')
            for label in labels:
                option = guide.get_by_role('button', name=f'{label} 포즈', exact=True)
                option.press('Enter')
                expect(option).to_have_attribute('aria-pressed', 'true')
                expect(guide.get_by_role('button', name='스케치 오른쪽 배치', exact=True)).to_have_attribute('aria-pressed', 'true')
                expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('선택한 인물 기준')
                silhouettes.add(pose.locator('svg path').evaluate_all("paths => paths.map(p => p.getAttribute('d')).join('|')"))
        assert len(silhouettes) == 12, 'All twelve choices must render different silhouettes'
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('사진 높이의 24%')
        crouched = pose.bounding_box()
        guide.get_by_role('button', name='서 있기 포즈 모음', exact=True).press('Enter')
        expect(guide.get_by_test_id('pose-scale-status')).to_contain_text('사진 높이의 40%')
        assert abs(pose.bounding_box()['height'] - crouched['height']) < 1, 'Crouching must not enlarge the head'
        mirror = guide.get_by_role('button', name='스케치 좌우 반전', exact=True)
        mirror.press('Space')
        expect(mirror).to_have_attribute('aria-pressed', 'true')
        expect(pose).to_have_attribute('aria-label', re.compile('좌우 반전'))
        assert '-1' in pose.locator('svg > g').get_attribute('transform'), 'Mirror must change the drawing'
        guide.get_by_test_id('pose-photo-frame').scroll_into_view_if_needed()
        page.screenshot(path=str(shots / '11_pose_variety.png'))
        first_url = image_url(first)
        gallery.scroll_into_view_if_needed()
        expect(gallery.get_by_test_id('photo-credit')).to_contain_text('사진 이용 조건')
        before = gallery.get_by_test_id('photo-credit').inner_text()
        click('다음 사진')
        expect(gallery).to_contain_text(f"2 / {candidate['n']}")
        loaded(first)
        assert image_url(first) != first_url, 'Next must show a different photo'
        assert before and gallery.get_by_test_id('photo-credit').inner_text()
        liked_url = image_url(first)
        like = gallery.get_by_test_id('photo-like')
        like.press('Enter')
        expect(like).to_have_attribute('aria-pressed', 'true')
        expect(gallery).to_contain_text(f"1 / {candidate['n']}")
        assert image_url(first) == liked_url, 'Ranking must keep the selected picture in view'
        expect(like).to_contain_text('좋아요 1')
        page.screenshot(path=str(shots / '12_photo_like.png'))
        like.press('Enter')
        expect(like).to_have_attribute('aria-pressed', 'false')
        expect(gallery).to_contain_text(f"2 / {candidate['n']}")
        click('이전 사진')
        expect(gallery).to_contain_text(f"1 / {candidate['n']}")
        page.screenshot(path=str(shots / ('09_photo_gallery_offline.png' if args.offline_images else '09_photo_gallery.png')))
        click('저장 ♡')
        visible(page.get_by_text('저장됨 ♥', exact=True)).wait_for()
        page.goto('http://localhost:8081/saved')
        expect(visible(page.get_by_text(candidate['name'], exact=True))).to_be_visible()
        expect(visible(page.get_by_test_id('place-photo-image'))).to_be_visible()
        loaded(visible(page.get_by_test_id('place-photo-image')))
        fallback_only = True
        page.goto('http://localhost:8081/place/' + candidate['id'] + '?date=2026-10-11')
        expect(visible(page.get_by_test_id('place-photo-source-links'))).to_contain_text('재사용 허용 공간 사진을 확인 중')
        expect(page.get_by_test_id('place-gallery').locator('visible=true')).to_have_count(0)
        expect(page.locator('iframe[src*="instagram.com"]')).to_have_count(0)
        assert not instagram_requests, 'Opening a place must not load Instagram scripts or embeds'
        assert not errors, errors
        print(f"PASS 12 distinct poses, keyboard selection, mirroring, person-relative scale, calibration, photo gallery, attribution, previous/next, saved cover; {candidate['name']} ({candidate['n']} photos)")
    finally:
        browser.close()
