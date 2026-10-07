"""UI smoke against the local app and its imported place catalog.

npm --prefix app run demo -- --port 8081
python app/e2e/release_smoke.py --channel chrome
"""
import argparse
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
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
        visible(page.get_by_role('checkbox')).click()
        click('체험용 로그인')
        text('기본 정보를 알려주세요').wait_for()
        fill('출생연도', '2099')
        click('다음')
        expect(text('출생연도를 확인해 주세요 (1900년~올해)')).to_be_visible()
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
        text('나를 살리는 빛').wait_for()
        expect(text('여름 쿨 라이트 · 웨이브 · 168.5cm · INFP')).to_be_visible()
        shot('03_result')
        click('추천 장소 보기')
        page.get_by_test_id('place-card').first.wait_for()
        expect(page.get_by_text('실제 장소 DB', exact=False)).to_have_count(0)
        expect(page.get_by_text('전체 수집:', exact=False)).to_have_count(0)
        expect(page.get_by_text('수집일', exact=False)).to_have_count(0)
        expect(visible(page.get_by_test_id('scoring-guide'))).to_contain_text('퍼스널컬러 40 · 체형 30 · 키 10 · MBTI 12')
        click('세부 가중치 보기')
        expect(text('조명 16 · 색온도 12 · 명도 6 · 채도 6')).to_be_visible()
        click('세부 가중치 접기')
        base_badge = page.get_by_test_id('place-card').first.get_by_test_id('recommendation-badge')
        expect(base_badge).to_have_text('정합도 100점')
        shot('04_home')
        def choose_group(label, group):
            with page.expect_response(lambda response: response.url.endswith('/preview/evaluate') and response.request.post_data_json.get('place_group') == group) as response:
                click(label)
            assert response.value.status == 200
            page.get_by_test_id('place-card').locator('visible=true').first.wait_for()
            assert evaluations[-1]['place_group'] == group
        choose_group('카페', 'cafe')
        for kind in page.get_by_test_id('place-kind').locator('visible=true').all():
            expect(kind).to_contain_text('카페')
        cafe = page.get_by_test_id('place-card').locator('visible=true').first
        expect(cafe.get_by_test_id('score-summary')).to_contain_text('퍼스널컬러 · 색온도 12점')
        cafe.click()
        expect(visible(page.get_by_test_id('score-details'))).to_contain_text('100 / 100점')
        expect(visible(page.get_by_test_id('score-metric-mbti_tf.photo_mood'))).to_contain_text('미평가')
        expect(visible(page.get_by_test_id('score-metric-pc_season.color_temp'))).to_contain_text('12 / 12점')
        visible(page.get_by_test_id('score-details')).scroll_into_view_if_needed()
        shot('04e_score_details')
        visible(page.get_by_label('목록으로', exact=True)).click()
        choose_group('축제·행사 공간', 'festival')
        for kind in page.get_by_test_id('place-kind').locator('visible=true').all():
            expect(kind).to_contain_text('행사 일정 확인 필요')
        shot('04c_event_spaces')
        page.get_by_test_id('place-card').locator('visible=true').first.click()
        visible(page.get_by_text('촬영일의 실제 행사 개최 여부', exact=False)).wait_for()
        text('원본 지도에서 장소 확인').wait_for()
        visible(page.get_by_label('목록으로', exact=True)).click()
        choose_group('여행 명소', 'travel')
        for kind in page.get_by_test_id('place-kind').locator('visible=true').all():
            expect(kind).not_to_contain_text('카페')
            expect(kind).not_to_contain_text('행사 일정 확인 필요')
        shot('04d_travel_places')
        expect(page.get_by_label('생년월일', exact=True).locator('visible=true')).to_have_count(0)
        assert evaluations and all(not request['use_saju'] for request in evaluations)
        first_base = page.get_by_test_id('place-card').locator('visible=true').first.get_by_test_id('place-name').inner_text()
        click('기본 추천만 볼게요')
        expect(page.get_by_text('사주·일진 추천도 추가로 볼까요?', exact=True).locator('visible=true')).to_have_count(0)
        click('촬영일·거리·시간')
        shoot_date('2026-10-10')
        click('검색 조건 닫기')
        click('사주·일진 추천 추가')
        expect(page).to_have_url(__import__('re').compile('/saju\\?'))
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
        for badge in extra_cards.get_by_test_id('recommendation-badge').all():
            expect(badge).to_have_text('토 추천')
        if extra_cards.count():
            extra_cards.first.click()
            expect(visible(page.get_by_test_id('recommendation-badge'))).to_have_text('토 추천')
            visible(page.get_by_label('목록으로', exact=True)).click()
            text('보완할 오행 · 화·토 (각 0%)').wait_for()
        saved = page.evaluate('localStorage.getItem("photospot.personal-preview.v1")')
        assert '1993-08-21' not in saved and 'birth_hour_branch' not in saved and 'pillars' not in saved
        click('촬영 날짜·사주 정보 변경')
        expect(visible(page.get_by_text('나의 대표 오행', exact=False))).to_be_visible()
        shoot_date('2026-10-13')
        click('오행·일진 장소 추천 보기')
        visible(page.get_by_text('2026-10-13 ·', exact=False)).wait_for()
        click('기본 추천으로 돌아가기')
        text('현재 적용: 기본 프로필 · 사주·일진 미반영').wait_for()
        page.get_by_test_id('place-card').locator('visible=true').first.wait_for()
        assert evaluations[-1]['use_saju'] is False
        assert evaluations[-1]['visit_date'] == '2026-10-10'
        assert evaluations[-1]['place_group'] == 'travel'
        assert page.get_by_test_id('place-card').locator('visible=true').first.get_by_test_id('place-name').inner_text() == first_base
        click('촬영일·거리·시간')
        click('아침')
        visible(page.get_by_text('시간대는 촬영 일정 참고용이에요.', exact=False)).wait_for()
        click('전체 시간')
        card = page.get_by_test_id('place-card').locator('visible=true').first
        name = card.get_by_test_id('place-name').inner_text()
        base_label = card.get_by_test_id('recommendation-badge').inner_text()
        assert re.fullmatch(r'정합도 \d+점', base_label)
        card.click()
        text('원본 지도에서 장소 확인').wait_for()
        expect(visible(page.get_by_test_id('recommendation-badge'))).to_have_text(base_label)
        expect(visible(page.get_by_test_id('score-details'))).to_contain_text('100 / 100점')
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
        text('나를 살리는 빛').wait_for()
        expect(text('겨울 쿨 딥 · 스트레이트 · 181cm · ENTJ')).to_be_visible()
        click('추천 장소 보기')
        click('내 정보 · 설정')
        text('사주 정보 삭제 및 동의 철회').wait_for()
        click('사주 정보 삭제 및 동의 철회')
        expect(page.get_by_text('사주 정보 삭제 및 동의 철회', exact=True).locator('visible=true')).to_have_count(0)
        click('회원 탈퇴')
        text('계정과 개인정보 영구 삭제').wait_for()
        shot('08_delete_confirmation')
        click('계정과 개인정보 영구 삭제')
        text('시작하기').wait_for()
        assert page.evaluate('localStorage.getItem("photospot.personal-preview.v1")') is None
        assert not errors, errors
        print('PASS all demo UI flows; zero page errors', flush=True)
    except Exception:
        shot('failure')
        print(page.locator('body').inner_text()[-4000:], flush=True)
        print('Page errors:', errors, flush=True)
        raise
    finally:
        browser.close()
