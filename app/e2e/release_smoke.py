"""UI smoke against the local app and its imported place catalog.

npm --prefix app run demo -- --port 8081
python app/e2e/release_smoke.py --channel chrome
"""
import argparse
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import datetime

# 촬영일 달력은 지난 날짜를 막으므로 고정 날짜 대신 가장 가까운 '일진 화(丙·丁)' 날을 고른다.
# 사주 구간의 기대값(보완 오행 토 우선 → 기차바위 1건, '토 추천')은 일진이 화인 날에 성립한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from saju.pillars import day_pillar  # noqa: E402

def fire_day():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    for offset in range(1, 15):
        day = today + datetime.timedelta(days=offset)
        if day_pillar(day).stem in (2, 3):
            return day.isoformat()
    raise AssertionError('14일 안에 일진 화인 날이 없음')
sys.stdout.reconfigure(encoding='utf-8')

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:8081')
parser.add_argument('--channel', default=None)
args = parser.parse_args()
shots = Path(__file__).resolve().parents[2] / 'artifacts' / 'screenshots'
shots.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=args.channel, headless=True)
    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='ko-KR',
                                  geolocation={'latitude': 37.5796, 'longitude': 126.977}, permissions=['geolocation'])
    page = context.new_page()
    page.set_default_timeout(15000)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    # React key collisions are console errors, not uncaught page exceptions.
    page.on('console', lambda message: errors.append(message.text)
            if message.type == 'error' and 'Encountered two children with the same key' in message.text else None)
    evaluations = []
    page.on('request', lambda request: evaluations.append(request.post_data_json) if request.url.endswith('/preview/evaluate') else None)
    visible = lambda locator: locator.locator('visible=true').last
    text = lambda label: visible(page.get_by_text(label, exact=True))
    click = lambda label: text(label).click()
    fill = lambda label, value: visible(page.get_by_label(label, exact=True)).fill(value)
    def shoot_date(value):
        visible(page.get_by_role('button', name='촬영일 달력 열기', exact=True)).click()
        year, month, _ = map(int, value.split('-'))
        current_year, current_month = map(int, re.findall(r'\d+', visible(page.get_by_test_id('calendar-month')).inner_text()))
        delta = (year - current_year) * 12 + month - current_month
        for _ in range(abs(delta)):
            visible(page.get_by_role('button', name='다음 달' if delta > 0 else '이전 달', exact=True)).click()
        visible(page.get_by_test_id('calendar-day-' + value)).click()
    def shot(name):
        page.screenshot(path=str(shots / f'{name}.png'), full_page=True)
        print(f'PASS {name}', flush=True)
    try:
        page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
        text('시작하기').wait_for(timeout=60000)
        shot('01_welcome')
        click('시작하기')
        page.get_by_role('checkbox').locator('visible=true').first.click()  # '모두 동의' (약관·개인정보·14세 일괄)
        click('추천 시작하기')
        text('기본 정보를 알려주세요').wait_for()
        fill('출생연도', '2099')
        click('다음')
        # 만 14세 기준: 허용 상한 연도가 해마다 바뀌므로 고정 문구 대신 안내 핵심만 확인한다
        expect(visible(page.get_by_role('alert'))).to_contain_text('만 14세 이상만 이용할 수 있어요')
        expect(visible(page.get_by_role('alert'))).to_contain_text('출생연도를 확인해 주세요')
        fill('출생연도', '1993')
        fill('키', '168.5')
        click('여성')
        click('다음')
        click('여름 쿨')
        click('라이트')
        click('웨이브')
        shot('02_style')
        click('다음')
        for letter in ['I', 'N', 'F', 'P']: click(letter)
        expect(page.get_by_role('switch')).to_have_count(0)
        expect(page.get_by_label('생년월일', exact=True)).to_have_count(0)
        click('추천 받기')
        text('여름 쿨 웨이브').wait_for()
        expect(text('여름 쿨 라이트 · 웨이브 · 168.5cm · INFP')).to_be_visible()
        shot('03_result')
        click('추천 장소 보기')
        page.get_by_test_id('place-card').first.wait_for()
        for label in ['처음으로', '♡ 저장한 장소', '내 정보 · 설정']:
            button = visible(page.get_by_role('button', name=label, exact=True))
            assert button.bounding_box()['height'] >= 44
        expect(page.get_by_text('실제 장소 DB', exact=False)).to_have_count(0)
        expect(page.get_by_text('전체 수집:', exact=False)).to_have_count(0)
        expect(page.get_by_text('수집일', exact=False)).to_have_count(0)
        guide = visible(page.get_by_role('button', name='정합도 판단 기준 상세', exact=True))
        expect(guide).to_have_attribute('aria-expanded', 'false')
        guide.click()
        expect(visible(page.get_by_test_id('scoring-guide'))).to_contain_text('퍼스널컬러 40 · 체형 30 · MBTI 30')
        expect(text('색온도 28 · 명도 6 · 채도 6')).to_be_visible()
        guide.click()
        expect(guide).to_have_attribute('aria-expanded', 'false')
        base_badge = page.get_by_test_id('place-card').first.get_by_test_id('recommendation-badge')
        # The fixture earns 34 of all 100 points; missing metrics must not inflate it to 100.
        expect(base_badge).to_have_text('정합도 42.5점')  # 희소 지표(E/I·S/N) 제외 80점 기준: 34/80
        for card in page.get_by_test_id('place-card').all():
            hours = card.get_by_test_id('hours-summary')   # 시간 정보가 없는 장소는 '미확인' 대신 줄 자체를 생략한다 (F018)
            if hours.count(): expect(hours).to_contain_text('운영시간')
            expect(card.get_by_test_id('place-distance')).to_contain_text('km')
            expect(card.get_by_test_id('score-summary')).to_have_count(0)
            expect(card.get_by_test_id('place-kind')).to_have_count(0)
        shot('04_home')
        def choose_group(label, group):
            with page.expect_response(lambda response: response.url.endswith('/preview/evaluate') and response.request.post_data_json.get('place_group') == group) as response:
                click(label)
            assert response.value.status == 200
            page.get_by_test_id('place-card').locator('visible=true').first.wait_for()
            assert evaluations[-1]['place_group'] == group
            items = response.value.json()['recommendations']['items']
            assert items and all(item['place_group'] == group for item in items)
            # Displayed total fit is primary for every basis; unknown goes last.
            scores = [item['fit_score'] if item['fit_score'] is not None else -1 for item in items]
            assert scores == sorted(scores, reverse=True)
            expect(page.get_by_test_id('place-card').locator('visible=true').get_by_test_id('place-name')).to_have_text([item['place_name'] for item in items])
        choose_group('카페 및 식당', 'cafe')
        cafe = page.get_by_test_id('place-card').locator('visible=true').first
        expect(cafe.get_by_test_id('recommendation-badge')).to_have_text('정합도 0점')
        cafe.click()
        expect(visible(page.get_by_test_id('score-total'))).to_have_text('0')
        expect(visible(page.get_by_test_id('score-pie'))).to_have_attribute('aria-label', re.compile('전체 정합도 0점'))
        metric = visible(page.get_by_test_id('score-metric-mbti_tf.space_nature'))
        expect(metric).to_contain_text('0 / 10점')
        expect(metric.get_by_role('button')).to_have_attribute('aria-expanded', 'false')
        metric.get_by_role('button').click()
        expect(metric).to_contain_text('건축물 중심')
        expect(visible(page.get_by_test_id('score-metric-pc_season.color_temp'))).to_contain_text('미평가')
        visible(page.get_by_test_id('score-details')).scroll_into_view_if_needed()
        shot('04e_score_details')
        visible(page.get_by_label('목록으로', exact=True)).click()
        choose_group('축제·행사 공간', 'festival')
        shot('04c_event_spaces')
        page.get_by_test_id('place-card').locator('visible=true').first.click()
        visible(page.get_by_text('촬영일의 실제 행사 개최 여부', exact=False)).wait_for()
        text('원본 지도에서 장소 확인').wait_for()
        visible(page.get_by_label('목록으로', exact=True)).click()
        choose_group('여행 명소', 'travel')
        shot('04d_travel_places')
        expect(page.get_by_label('생년월일', exact=True).locator('visible=true')).to_have_count(0)
        assert evaluations and all(not request['use_saju'] for request in evaluations)
        first_base = page.get_by_test_id('place-card').locator('visible=true').first.get_by_test_id('place-name').inner_text()
        click('기본 추천만 볼게요')
        expect(page.get_by_text('사주·일진 추천도 추가로 볼까요?', exact=True).locator('visible=true')).to_have_count(0)
        click('촬영일·거리·시간')
        shoot = fire_day()                       # 사주 구간 촬영일 (일진 화)
        shoot_date(shoot)
        click('검색 조건 닫기')
        click('사주·일진 추천 추가')
        expect(page).to_have_url(re.compile(r'/saju\?'))
        text('나의 오행과 촬영일에 맞는 장소').wait_for()
        assert all(not request['use_saju'] for request in evaluations)
        fill('생년월일', '19930821')
        expect(visible(page.get_by_label('생년월일', exact=True))).to_have_value('1993-08-21')
        hour = visible(page.get_by_role('combobox', name='태어난 시', exact=True))
        expect(hour.locator('option')).to_have_count(13)
        hour.select_option('zi')
        expect(hour).to_have_value('zi')
        click('오행·일진 장소 추천 보기')
        expect(text('오행을 계산하려면 생년월일시 사용에 동의해 주세요')).to_be_visible()
        visible(page.get_by_label('오행 계산 동의', exact=True)).click()
        visible(page.get_by_label('생년월일', exact=True)).scroll_into_view_if_needed()
        shot('04a_shoot_conditions')
        click('오행·일진 장소 추천 보기')
        text('보완할 오행 · 화·토 (각 0%)').wait_for()
        assert evaluations[-1]['use_saju'] and evaluations[-1]['percents']['fire'] == 0
        assert evaluations[-1]['place_group'] == 'travel'
        expect(page.get_by_label('생년월일', exact=True).locator('visible=true')).to_have_count(0)
        text('보완할 오행 · 화·토 (각 0%)').scroll_into_view_if_needed()
        shot('04b_daily_personal')
        extra_cards = page.get_by_test_id('place-card').locator('visible=true')
        expect(extra_cards).to_have_count(1)
        expect(extra_cards.first.get_by_test_id('place-name')).to_have_text('기차바위')
        expect(extra_cards.first.get_by_test_id('recommendation-badge')).to_have_text('정합도 12.5점')  # 분류 추정 T/F 10/80
        extra_label = extra_cards.first.get_by_test_id('recommendation-badge').inner_text()
        extra_cards.first.click()
        # Detail uses an element badge; its numeric pie must match the feed's fit.
        expect(visible(page.get_by_test_id('recommendation-badge'))).to_have_text('토 추천')
        expect(visible(page.get_by_test_id('score-total'))).to_have_text(extra_label.removeprefix('정합도 ').removesuffix('점'))
        expect(visible(page.get_by_text('오행 종합', exact=False))).to_be_visible()
        visible(page.get_by_label('목록으로', exact=True)).click()
        text('보완할 오행 · 화·토 (각 0%)').wait_for()
        saved = page.evaluate('localStorage.getItem("photospot.personal-preview.v1")')
        assert '1993-08-21' not in saved and 'birth_hour_branch' not in saved and 'pillars' not in saved
        click('촬영 날짜·사주 정보 변경')
        expect(visible(page.get_by_text('나의 대표 오행', exact=False))).to_be_visible()
        shoot2 = (datetime.date.fromisoformat(shoot) + datetime.timedelta(days=3)).isoformat()
        shoot_date(shoot2)
        click('오행·일진 장소 추천 보기')
        visible(page.get_by_text(shoot2 + ' ·', exact=False)).wait_for()
        click('기본 추천으로 돌아가기')
        text('현재 적용: 기본 프로필 · 사주·일진 미반영').wait_for()
        page.get_by_test_id('place-card').locator('visible=true').first.wait_for()
        assert evaluations[-1]['use_saju'] is False
        assert evaluations[-1]['visit_date'] == shoot
        assert evaluations[-1]['place_group'] == 'travel'
        assert page.get_by_test_id('place-card').locator('visible=true').first.get_by_test_id('place-name').inner_text() == first_base
        click('촬영일·거리·시간')
        click('아침')
        visible(page.get_by_text('시간대는 촬영 일정 참고용이에요.', exact=False)).wait_for()
        click('전체 시간')
        card = page.get_by_test_id('place-card').locator('visible=true').first
        name = card.get_by_test_id('place-name').inner_text()
        base_label = card.get_by_test_id('recommendation-badge').inner_text()
        assert re.fullmatch(r'정합도 \d+(?:\.\d+)?점', base_label)
        card.click()
        text('원본 지도에서 장소 확인').wait_for()
        expect(visible(page.get_by_test_id('recommendation-badge'))).to_have_text(base_label)
        expect(visible(page.get_by_test_id('score-total'))).to_have_text(base_label.removeprefix('정합도 ').removesuffix('점'))
        expect(visible(page.get_by_test_id('score-metric-body_type.form'))).to_contain_text('미평가')
        expect(page.get_by_text('수집일', exact=False)).to_have_count(0)
        expect(text('추천 이유')).to_be_visible()
        click('저장 ♡')
        text('저장됨 ♥').wait_for()
        shot('05_place_saved')
        visible(page.get_by_label('목록으로', exact=True)).click()
        text('오늘 어디서 찍을까요').wait_for()
        click('♡ 저장한 장소')
        text(name).wait_for()
        shot('06_saved')
        click('추천 장소로 돌아가기')
        click('내 정보 · 설정')
        text('프로필 수정하기').wait_for()
        shot('07_settings')
        page.reload(wait_until='domcontentloaded')
        expect(visible(page.get_by_text('성별 여성 · 출생연도 1993년 · 키 168.5cm', exact=True))).to_be_visible()
        click('프로필 수정하기')
        expect(visible(page.get_by_label('키', exact=True))).to_have_value('168.5')
        fill('키', '181')
        click('남성')
        click('다음')
        click('겨울 쿨')
        click('딥')
        click('스트레이트')
        click('다음')
        for letter in ['E', 'N', 'T', 'J']: click(letter)
        click('추천 받기')
        text('겨울 쿨 스트레이트').wait_for()
        expect(text('겨울 쿨 딥 · 스트레이트 · 181cm · ENTJ')).to_be_visible()
        click('추천 장소 보기')
        click('내 정보 · 설정')
        text('사주 정보 삭제 및 동의 철회').wait_for()
        click('사주 정보 삭제 및 동의 철회')
        expect(page.get_by_text('사주 정보 삭제 및 동의 철회', exact=True).locator('visible=true')).to_have_count(0)
        click('이 브라우저의 데이터 삭제')
        text('브라우저 데이터 삭제 확인').wait_for()
        shot('08_delete_confirmation')
        click('브라우저 데이터 삭제 확인')
        text('시작하기').wait_for()
        assert page.evaluate('localStorage.getItem("photospot.personal-preview.v1")') is None

        # Start over is separate from account deletion and must clear every personal input.
        click('시작하기')
        page.get_by_role('checkbox').locator('visible=true').first.click()  # '모두 동의' (약관·개인정보·14세 일괄)
        click('추천 시작하기')
        fill('출생연도', '1993')
        fill('키', '168.5')
        click('여성')
        click('다음')
        click('여름 쿨')
        click('라이트')
        click('웨이브')
        click('다음')
        for letter in ['I', 'N', 'F', 'P']: click(letter)
        click('추천 받기')
        click('추천 장소 보기')
        click('사주·일진 추천 추가')
        fill('생년월일', '19930821')
        visible(page.get_by_role('combobox', name='태어난 시', exact=True)).select_option('zi')
        visible(page.get_by_label('오행 계산 동의', exact=True)).click()
        click('오행·일진 장소 추천 보기')
        text('보완할 오행 · 화·토 (각 0%)').wait_for()
        click('처음으로')
        click('초기화하고 처음으로')                     # 확인 카드(F021)를 거쳐야 초기화된다
        expect(page).to_have_url(args.url.rstrip('/') + '/')
        text('시작하기').wait_for()
        state = page.evaluate('JSON.parse(localStorage.getItem("photospot.personal-preview.v1"))')
        assert state['profile'] is None and state['saju'] is None
        assert page.evaluate('localStorage.getItem("photospot.demo.tokens")') is None
        page.reload(wait_until='domcontentloaded')
        click('시작하기')
        page.get_by_role('checkbox').locator('visible=true').first.click()  # '모두 동의' (약관·개인정보·14세 일괄)
        click('추천 시작하기')
        expect(visible(page.get_by_label('출생연도', exact=True))).to_have_value('')
        expect(visible(page.get_by_label('키', exact=True))).to_have_value('')
        click('다음')
        click('다음')
        click('추천 받기')
        click('추천 장소 보기')
        text('오늘 어디서 찍을까요').wait_for()
        # Empty wizard values must not reload the old draft, even after a page reload.
        profile = page.evaluate('JSON.parse(localStorage.getItem("photospot.personal-preview.v1")).profile')
        assert profile['gender'] == 'undisclosed'
        assert all(profile[key] is None for key in ['birth_year', 'height_cm', 'pc_season', 'pc_subtone', 'body_type', 'mbti'])
        click('처음으로')
        click('초기화하고 처음으로')
        text('시작하기').wait_for()
        expect(page).to_have_url(args.url.rstrip('/') + '/')
        shot('09_start_over')
        assert not errors, errors
        print('PASS all demo UI flows; zero page errors', flush=True)
    except Exception:
        shot('failure')
        print(page.locator('body').inner_text()[-4000:], flush=True)
        print('Page errors:', errors, flush=True)
        raise
    finally:
        browser.close()
