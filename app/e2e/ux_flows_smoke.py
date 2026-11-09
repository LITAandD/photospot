"""UX 흐름 스모크 (ux-flows): 딥링크 복귀(F023), 온보딩 보존(F022·F104), 자가진단 닫기(F077), 공유 폴백(F011·S-2), 없는 장소(S-7),
달력 과거 금지(S-4), '처음으로' 확인(F021), 익명 계측 payload(F031), 웹 aria 상태(S-3), 공유 메타·정적 자산(F029·D-5).
서버: PHOTOSPOT_WEB (기본 http://localhost:8081) — DEMO 웹 빌드를 deploy/vercel/index.py 로 서빙한 주소(build-web-preview.cjs 후처리 포함)."""
import base64
import datetime as dt
import json
import os
import re

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('PHOTOSPOT_WEB', 'http://localhost:8081').rstrip('/')
PID = os.environ.get('PHOTOSPOT_PID_PHOTO', 'cf314fda-c042-552a-918d-1453127e24e1')   # 창덕궁: 사진 있는 장소
PUBLIC = 'https://photospot.litaandd.com'
KST_NOW = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
TODAY = KST_NOW.strftime('%Y-%m-%d')
YESTERDAY = (KST_NOW - dt.timedelta(days=1)).strftime('%Y-%m-%d')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
KEYS = {'event', 'route', 'session_id', 'utm', 'props'}


def new_context(browser, events):
    ctx = browser.new_context(locale='ko-KR', viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                              geolocation={'latitude': 37.5796, 'longitude': 126.977},
                              permissions=['geolocation', 'clipboard-read', 'clipboard-write'])
    # Web Share 가 없는 브라우저(데스크톱 파이어폭스·리눅스 크롬)를 재현한다 → 클립보드 폴백
    ctx.add_init_script("try { Object.defineProperty(navigator, 'share', { value: undefined, configurable: true }); } catch (e) {}")
    ctx.route(lambda u: any(h in u for h in ['wikimedia.org', 'pstatic.net', 'istarbucks', 'poxo.com', 'visitbusan']),
              lambda r: r.fulfill(status=200, body=PNG, headers={'content-type': 'image/png', 'access-control-allow-origin': '*'}))
    ctx.on('request', lambda r: events.append(json.loads(r.post_data)) if r.url.endswith('/preview/events') and r.post_data else None)
    ctx.set_default_timeout(20000)
    return ctx


def login(page):
    expect(page.get_by_text('체험용 로그인', exact=True)).to_be_visible()
    box = page.get_by_role('checkbox').first                                   # '모두 동의'
    expect(box).to_have_attribute('aria-checked', 'false')                      # S-3: 체크 상태가 DOM 에 드러난다
    box.click()
    expect(box).to_have_attribute('aria-checked', 'true')
    page.get_by_text('체험용 로그인', exact=True).click()


def onboard(page, fill):
    expect(page).to_have_url(re.compile('/onboarding/basic'))
    if fill:
        page.get_by_text('여성', exact=True).click()
        page.get_by_placeholder('예: 1998').fill('1993')
        page.get_by_placeholder('예: 162').fill('162')
    page.get_by_role('button', name='다음', exact=True).click()
    expect(page).to_have_url(re.compile('/onboarding/style'))
    if fill:
        page.get_by_role('button', name=re.compile('^봄 웜')).click()
        page.get_by_role('button', name=re.compile('스트레이트')).click()
    page.get_by_role('button', name='다음', exact=True).click()
    expect(page).to_have_url(re.compile('/onboarding/traits'))
    if fill:
        for letter in 'ENFP':
            page.get_by_text(letter, exact=True).click()
    page.get_by_role('button', name='추천 받기', exact=True).click()


def toast(page):
    return page.get_by_role('status').filter(has_text='복사했어요')


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    events = []

    # --- 공유 메타·정적 자산 (F029·D-5) ----------------------------------------------------------
    ctx = new_context(browser, events)
    for path, kind in [('/og.png', 'image/png'), ('/favicon.ico', 'image/'), ('/apple-touch-icon.png', 'image/png'), ('/manifest.json', 'application/json')]:
        r = ctx.request.get(BASE + path)
        assert r.status == 200 and r.headers.get('content-type', '').startswith(kind), (path, r.status, r.headers.get('content-type'))
    assert json.loads(ctx.request.get(BASE + '/manifest.json').text())['name'] == '포토스팟'
    html = ctx.request.get(BASE + '/place/' + PID).text()                             # SPA 경로도 같은 머리말을 받는다
    for tag in ['property="og:title"', 'property="og:image" content="%s/og.png"' % PUBLIC, 'name="twitter:card" content="summary_large_image"',
                'name="description"', 'rel="canonical"', 'rel="icon"', 'rel="apple-touch-icon"', 'rel="manifest"', 'name="theme-color"']:
        assert tag in html, tag

    # --- A. 비로그인 장소 딥링크 → 로그인 → 온보딩(프로필 입력) → 그 장소로 복귀 (F023·S-5) ------------
    page = ctx.new_page()
    page.goto(f'{BASE}/place/{PID}?date={TODAY}')
    expect(page).to_have_url(re.compile('/login'))
    login(page)
    onboard(page, fill=True)
    expect(page).to_have_url(re.compile(f'/place/{PID}'))
    expect(page.get_by_text('이 장소 공유하기', exact=True)).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('photospot.intended-route')") is None
    # 기본 경로: 로그인 뒤 홈 — 기억한 주소가 없을 때는 그대로 홈에 머문다 (DeepLinkKeeper 가 엉뚱하게 되돌리지 않음)
    page.goto(BASE + '/home')
    page.wait_for_timeout(800)
    expect(page).to_have_url(re.compile('/home$'))
    assert page.evaluate("document.querySelector('link[rel=canonical]').href") == PUBLIC + '/home'      # 경로별 canonical
    assert page.evaluate("document.querySelector('meta[property=\"og:url\"]').content") == PUBLIC + '/home'

    # --- C1. 로그인 사용자는 대문에서 바로 홈으로 (F081) ------------------------------------------
    page.goto(BASE + '/')
    expect(page).to_have_url(re.compile('/home$'))

    # --- C2. 자가진단 딥링크의 닫기: 프로필이 있으면 홈으로 (F077·F022) ----------------------------
    page.goto(BASE + '/diagnosis/personal-color')
    expect(page.get_by_text('질문 1 /', exact=False)).to_be_visible()
    page.wait_for_timeout(800)                                                 # 기존 프로필을 초안으로 불러올 시간
    page.get_by_role('button', name='닫기', exact=True).click()
    expect(page).to_have_url(re.compile('/home$'))

    # --- C3. 새로고침·딥링크 뒤 온보딩을 이어 가도 기존 값이 지워지지 않고, 바꾼 값은 새로고침을 견딘다 (F022·F104) ---
    page.goto(BASE + '/onboarding/style')
    expect(page.get_by_role('button', name=re.compile('^봄 웜'))).to_have_attribute('aria-pressed', 'true')   # 저장값이 미리 선택됨
    page.get_by_role('button', name=re.compile('^여름 쿨')).click()
    expect(page.get_by_role('button', name=re.compile('^여름 쿨'))).to_have_attribute('aria-pressed', 'true')
    page.reload()
    expect(page.get_by_role('button', name=re.compile('^여름 쿨'))).to_have_attribute('aria-pressed', 'true')   # 초안이 sessionStorage 에 남음
    page.get_by_role('button', name='다음', exact=True).click()
    expect(page).to_have_url(re.compile('/onboarding/traits'))
    page.get_by_role('button', name='추천 받기', exact=True).click()
    expect(page).to_have_url(re.compile('/result'))
    page.goto(BASE + '/settings')
    expect(page.get_by_text('출생연도', exact=False).first).to_be_visible()            # 프로필 요약이 로드된 뒤 읽는다
    settings = page.locator('body').inner_text()
    for word in ['1993', '162', '여름 쿨', 'ENFP', '여성']:
        assert word in settings, (word, settings[:400])
    assert '미입력' not in settings and '선택 안 함' not in settings, settings[:400]

    # --- C4. 결과 카드 공유: Web Share 없음 → 클립보드 + 토스트, 주소에 utm (F011·S-2·N-growth-2) --------
    page.goto(BASE + '/result')
    share = page.get_by_role('button', name='결과 카드 공유하기', exact=True)
    expect(share).to_be_visible()
    share.click()
    expect(toast(page)).to_be_visible()
    copied = page.evaluate('navigator.clipboard.readText()')
    assert '나의 포토 타입' in copied and f'{PUBLIC}/?utm_medium=result_card&utm_source=share' in copied, copied
    assert '잘 맞는 빛: \n' not in copied and not re.search(r': *\n', copied), copied        # 빈 줄 없음

    # --- C5. 장소 공유·저장·포즈 가이드 키보드 (F070·F078·N-accessibility-1) ------------------------------
    page.goto(f'{BASE}/place/{PID}?date={TODAY}')
    page.get_by_role('button', name='이 장소 공유하기', exact=True).click()
    expect(toast(page)).to_be_visible()
    copied = page.evaluate('navigator.clipboard.readText()')
    assert f'{PUBLIC}/place/{PID}?utm_medium=place&utm_source=share' in copied, copied
    page.get_by_role('button', name='저장 ♡', exact=True).click()
    expect(page.get_by_role('button', name='저장됨 ♥', exact=True)).to_be_visible()
    fit = page.get_by_role('button', name='사진 속 사람 크기에 맞추기', exact=True)
    pose_checked = False
    if fit.count():
        fit.click()
        page.get_by_label('인물 머리 위치 (%)').fill('20')
        foot = page.get_by_label('인물 발끝 위치 (%)')
        foot.fill('60')
        foot.press('Enter')                                                      # Enter = 적용
        expect(page.get_by_test_id('pose-scale-status')).to_contain_text('선택한 인물 기준')
        assert page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-label')") == '사진 속 사람 크기에 맞추기'
        pose_checked = True

    # --- C6. 저장 목록 비우기 (S-11) ------------------------------------------------------------
    page.goto(BASE + '/saved')
    page.get_by_role('button', name='저장 목록 비우기', exact=True).click()
    page.get_by_role('button', name='모두 지우기', exact=True).click()
    expect(page.get_by_text('아직 저장한 장소가 없어요', exact=False)).to_be_visible()

    # --- C7. 없는 장소: 자리표시 없이 안내 카드만, noindex (S-7·F077) ------------------------------
    page.goto(BASE + '/place/does-not-exist')
    expect(page.get_by_text('장소를 찾을 수 없어요', exact=True)).to_be_visible()
    assert page.get_by_text('대표 사진 준비 중', exact=True).count() == 0
    assert page.get_by_test_id('place-pose-guide').count() == 0
    assert page.evaluate("document.querySelector('meta[name=robots]') && document.querySelector('meta[name=robots]').content") == 'noindex'
    assert '찾을 수 없어요' in page.title()
    page.get_by_role('button', name='추천 목록으로 돌아가기', exact=True).click()
    expect(page).to_have_url(re.compile('/home$'))
    assert page.evaluate("document.querySelector('meta[name=robots]')") is None

    # --- C8. 홈: 달력 과거 금지 + aria 상태, 칩 aria-pressed (S-4·S-3) ------------------------------
    filters = page.get_by_role('button', name='촬영일·거리·시간', exact=True)       # 달력은 접힌 필터 안에 있다
    if filters.count():
        filters.click()
    toggle = page.get_by_role('button', name='촬영일 달력 열기', exact=True)
    expect(toggle).to_have_attribute('aria-expanded', 'false')
    toggle.click()
    expect(toggle).to_have_attribute('aria-expanded', 'true')
    expect(page.get_by_role('button', name='이전 달', exact=True)).to_have_attribute('aria-disabled', 'true')
    if YESTERDAY[:7] == TODAY[:7]:
        expect(page.get_by_test_id(f'calendar-day-{YESTERDAY}')).to_have_attribute('aria-disabled', 'true')
    expect(page.get_by_test_id(f'calendar-day-{TODAY}')).not_to_have_attribute('aria-disabled', 'true')
    toggle.click()
    assert page.locator('[role=button][aria-pressed]').count() > 0

    # --- C9. 처음으로: 확인 창 → 취소는 무해, 확인하면 초기화·로그아웃·대문 (F021) -------------------------
    page.get_by_role('button', name='처음으로', exact=True).click()
    expect(page.get_by_role('alertdialog')).to_be_visible()
    assert page.evaluate("localStorage.getItem('photospot.personal-preview.v1')") is not None
    page.get_by_role('button', name='취소', exact=True).click()
    expect(page.get_by_role('alertdialog')).to_have_count(0)
    expect(page).to_have_url(re.compile('/home$'))
    page.get_by_role('button', name='처음으로', exact=True).click()
    page.get_by_role('button', name='초기화하고 처음으로', exact=True).click()
    expect(page).to_have_url(BASE + '/')
    state = page.evaluate("JSON.parse(localStorage.getItem('photospot.personal-preview.v1') || '{}')")
    assert state.get('profile') is None and state.get('saju') is None, state
    ctx.close()

    # --- B. 비로그인 자가진단 딥링크 → 로그인 → 온보딩 건너뛰기 → 자가진단으로 복귀 (F023) ------------
    ctx = new_context(browser, events)
    page = ctx.new_page()
    page.goto(BASE + '/diagnosis/personal-color')
    expect(page).to_have_url(re.compile('/login'))
    login(page)
    onboard(page, fill=False)
    expect(page).to_have_url(re.compile('/diagnosis/personal-color$'))
    expect(page.get_by_text('질문 1 /', exact=False)).to_be_visible()
    # 자리표시 카드(타입 미확정)에서는 공유 대신 프로필 입력 안내 (N-growth-2)
    page.goto(BASE + '/result')
    expect(page.get_by_role('button', name='프로필 입력하고 타입 보기', exact=True)).to_be_visible()
    assert page.get_by_role('button', name='결과 카드 공유하기', exact=True).count() == 0
    ctx.close()

    # --- 계측 payload: 허용된 키만, 경로에 쿼리 없음, 개인정보 없음 (F031) ----------------------------
    assert events, '계측 이벤트가 하나도 전송되지 않았어요'
    names = {e['event'] for e in events}
    for e in events:
        assert set(e) == KEYS, e
        assert re.fullmatch(r'/[^\s?#]*', e['route']), e
        assert re.fullmatch(r'[A-Za-z0-9_-]{8,64}', e['session_id']), e
        assert '1993' not in json.dumps(e) and 'ENFP' not in json.dumps(e), e
    for name in ['landing_view', 'place_view', 'result_view', 'share_click', 'save']:
        assert name in names, (name, names)
    assert any(e['event'] == 'share_click' and e['props'].get('outcome') == 'copied' for e in events)
    assert len({e['session_id'] for e in events}) == 2, '컨텍스트(브라우저)마다 세션 ID 하나'
    browser.close()
    print(f'PASS ux flows: deep links return, onboarding preserved, share fallback, not-found noindex, calendar, start-over confirm, '
          f'{len(events)} analytics events ({sorted(names)}), pose guide keyboard={"checked" if pose_checked else "skipped (no photo)"}')
