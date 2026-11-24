"""Local-only, same-origin cut-finder scenarios; never sends events to production."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8320')
args = parser.parse_args()
assert urlparse(args.url).hostname in {'localhost', '127.0.0.1'}
base = args.url.rstrip('/')
day = (datetime.now(timezone.utc) + timedelta(hours=9,days=1)).date().isoformat()
out = Path('artifacts/today-shot-ui'); out.mkdir(parents=True, exist_ok=True)
results = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for width in [360, 390, 1280]:
        ctx = browser.new_context(viewport={'width': width, 'height': 844}, locale='ko-KR')
        ctx.grant_permissions(['clipboard-read','clipboard-write'])
        ctx.add_init_script("localStorage.setItem('photospot.analytics.choice.v2','allow');localStorage.setItem('photospot.analytics.shots.v1','allow')")
        ctx.add_init_script("Object.defineProperty(navigator, 'share', {value:undefined,configurable:true})")
        events, errors = [], []
        def guard(route):
            if '/preview/events' in route.request.url:
                events.append(route.request.post_data_json)
                route.fulfill(status=204)
            else:
                route.continue_()
        ctx.route('**/*', guard)
        page = ctx.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f'{base}/browse?city=seoul&date={day}')
        expect(page.get_by_role('button', name='오늘의 한 컷 열기', exact=True)).to_have_count(0)
        page.goto(f'{base}/today-shot?date={day}')
        expect(page.get_by_role('heading', level=1, name='오늘의 한 컷')).to_be_visible()
        expect(page.get_by_role('heading', name='이 조건에서 확인된 컷이 없어요', exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_test_id('shot-card')).to_have_count(0)
        assert '/login' not in page.url
        expect(page.get_by_role('status')).to_have_count(1)
        assert page.get_by_role('heading',name='이 조건에서 확인된 컷이 없어요',exact=True).bounding_box()['y'] < 600
        page.wait_for_timeout(200)
        assert len([e for e in events if e['event']=='shot_view' and e['props']['result']=='empty']) == 1
        events.clear()
        page.screenshot(path=str(out/f'{width}-pending.png'), full_page=True)
        page.get_by_role('button', name='검토용 시나리오 보기').click()
        page.get_by_role('button', name='테스트 · 정상 개방', exact=True).click()
        card = page.get_by_test_id('shot-card')
        expect(card).to_be_visible(timeout=30000)
        expect(page.get_by_text('검토용 합성 예시 · 현장 안내 아님',exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        card.evaluate("el => el.scrollIntoView({block:'start'})")
        page.screenshot(path=str(out/f'{width}-guide.png'))
        card.get_by_role('button', name='카카오맵으로 길찾기',exact=True).click()
        expect(page.get_by_text('길찾기 테스트 완료',exact=False)).to_be_visible()
        assert len(ctx.pages) == 1
        card.get_by_role('button',name='이 컷 공유하기',exact=True).click()
        expect(page.get_by_text('링크와 내용을 복사했어요.',exact=False)).to_be_visible()
        shared = page.evaluate('navigator.clipboard.readText()').splitlines()[-1]
        q = parse_qs(urlparse(shared).query)
        assert q['date'] == [day] and q['cut'] == ['test-cut-a'] and q['review'] == ['open']
        fresh = browser.new_context(viewport={'width':width,'height':844})
        fresh.add_init_script("localStorage.setItem('photospot.analytics.choice.v2','allow');localStorage.setItem('photospot.analytics.shots.v1','allow')")
        fresh.route('**/*',guard)
        fresh_page = fresh.new_page(); fresh_page.goto(shared)
        expect(fresh_page.get_by_test_id('shot-card')).to_be_visible(timeout=30000)
        assert 'cut=test-cut-a' in fresh_page.url and day in fresh_page.url
        assert fresh_page.get_by_role('button',name='카카오맵으로 길찾기',exact=True).bounding_box()['y'] < 844
        fresh_page.screenshot(path=str(out/f'{width}-first-screen.png'))
        fresh_page.get_by_role('button',name='안내대로 찍었어요',exact=True).click()
        fresh_page.reload()
        expect(fresh_page.get_by_role('button',name='확인했어요 · 감사합니다')).to_be_disabled(timeout=30000)
        fresh.close()
        card.get_by_role('button',name='안내대로 찍었어요',exact=True).click()
        expect(card.get_by_role('button',name='확인했어요 · 감사합니다')).to_be_disabled()
        page.screenshot(path=str(out/f'{width}-actions.png'))
        for case, label in [('weekly_closed','정기 휴무'),('temporary_closed','임시 통제'),('cutoff','입장마감 전후')]:
            page.get_by_role('button',name=f'테스트 · {label}',exact=True).click()
            expect(page.get_by_test_id('shot-card')).to_have_count(0)
            alternative = page.get_by_role('button',name='대체 컷 열기',exact=True)
            expect(alternative).to_be_visible(timeout=30000)
            alternative.click()
            expect(card).to_contain_text('검토 예시 B',timeout=30000)
            expect(page.get_by_test_id('shot-result')).to_be_focused()
        page.get_by_role('button',name='테스트 · 입장마감 전후',exact=True).click()
        page.get_by_role('button',name='조건 바꾸기',exact=True).click()
        expect(page.get_by_role('button',name='조건 접기',exact=True)).to_have_attribute('aria-expanded','true')
        field=page.get_by_role('textbox',name='방문 시각 직접 입력 (HH:MM, 선택)',exact=True)
        field.fill('1')
        expect(page.get_by_role('button',name='대체 컷 열기',exact=True)).to_be_visible()
        expect(field).to_have_attribute('aria-invalid','false')
        field.fill('9:30');field.press('Tab')
        expect(page).to_have_url(__import__('re').compile('time=09%3A30'))
        field.fill('1530');field.press('Tab')
        expect(page).to_have_url(__import__('re').compile('time=15%3A30'))
        field.fill('25:00');field.press('Tab')
        expect(field).to_have_attribute('aria-invalid','true')
        expect(card).to_be_visible()
        field.fill('15:59');field.press('Tab')
        expect(card).to_contain_text('검토 예시 A',timeout=30000)
        field.fill('16:00');field.press('Tab')
        expect(page.get_by_role('button',name='대체 컷 열기',exact=True)).to_be_visible(timeout=30000)
        for label in ['운영정보 미확인','대체 컷 없음']:
            page.get_by_role('button',name=f'테스트 · {label}',exact=True).click()
            expect(page.get_by_role('heading', name='이 조건에서 확인된 컷이 없어요',exact=True)).to_be_visible(timeout=30000)
            expect(card).to_have_count(0)
            expect(page.get_by_role('button',name='대체 컷 열기',exact=True)).to_have_count(0)
        # A later response must never leave the previous actionable card in view.
        page.get_by_role('button',name='테스트 · 정상 개방',exact=True).click()
        expect(card).to_be_visible(timeout=30000)
        field.fill('');field.press('Tab')
        expect(card).to_contain_text('방문 시간 미선택',timeout=30000)
        before=page.get_by_role('status').inner_text()
        page.get_by_role('button',name='저녁 6시',exact=True).click()
        expect(page.get_by_role('status')).not_to_have_text(before)
        expect(page.get_by_role('button',name='저녁 6시',exact=True)).to_be_focused()
        page.get_by_role('button',name='선택한 컷 해제하고 다시 찾기',exact=True).click()
        expect(page.get_by_test_id('shot-result')).to_be_focused()
        shot_events = [e for e in events if e['event'].startswith('shot_')]
        assert not shot_events and not errors, (shot_events,errors)
        results.append({'width':width,'scenarios':6,'share_same_cut_date':True,'unauthenticated':True,'events':0,'errors':errors})
        ctx.close()
    browser.close()
out.joinpath('results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=False))
