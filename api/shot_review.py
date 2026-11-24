"""Synthetic UI examples, never actual field evidence. Endpoint is preview/test-only."""
from datetime import timedelta, time
from .shot_guides import Place
from pipeline.catalog_visitors import today


def fixture_places(case, visit):
    source = {'label': '기능 검수용 합성 자료 · 실제 이용 근거 아님', 'url': 'https://example.org/shot-test',
              'checked_at': min(visit, today()) - timedelta(days=1), 'valid_until': max(visit, today()) + timedelta(days=2)}
    window = {'opens': '09:00', 'closes': '17:00', 'last_entry': '16:00'}
    def make(suffix, name):
        schedule = {'source': source, 'weekdays': {str(i): [window] for i in range(7)},
                    'applies_from': source['checked_at'], 'applies_until': source['valid_until'], 'note': '테스트 시간표 · 현장 안내로 사용하지 마세요'}
        return Place.model_validate({'place_id': 'test-place-' + suffix, 'name': name,
            'place_schedule': schedule, 'cuts': [{'id': 'test-cut-' + suffix, 'title': '기준물을 중앙에 담는 건축 컷',
                'status': 'verified', 'pin': {'lat': 37.57, 'lng': 126.97, 'standing_landmark': '테스트 도식의 주황색 촬영자 표시',
                    'bearing_deg': 0, 'look_toward': '테스트 도식의 중앙 건물', 'entry_instructions': '테스트 보행로를 따라 촬영자 표시로 이동 · 실제 경로 아님',
                    'method': 'field_gnss_and_landmark', 'accuracy_m': 5},
                'framing': '휴대폰 1배 · 세로 · 건물을 중앙에 맞추고 윗부분에 여백을 남겨요',
                'parties': ['solo', 'pair', 'family'], 'goals': ['architecture', 'portrait'],
                'visual': {'kind': 'diagram', 'composition': {'subject':'architecture','orientation':'portrait','subject_x':0.5}, 'creator': 'LIT A&D', 'rights': '자체 제작 구도 도식 · 실제 장소 형상 아님'},
                'field_review': {'checked_at': source['checked_at'], 'valid_until': source['valid_until'],
                    'record_ref': 'synthetic-test-only', 'independent_measurement': True, 'first_time_tester_found_pin': True, 'framing_reproduced': True, 'safe_standing_area': True},
                'access': schedule, 'photography': source, 'photography_allowed': True, 'restrictions': '테스트 제한 안내 · 현장 촬영 허용을 뜻하지 않아요'}]})
    first, second = make('a', '검토 예시 A · 궁궐 내부'), make('b', '검토 예시 B · 광장 외부')
    if case == 'weekly_closed':
        first.place_schedule.weekdays[str(visit.weekday())] = []
    if case in ('temporary_closed', 'no_alternative'):
        first.cuts[0].access.exceptions[visit] = []
        first.cuts[0].access.exception_notes[visit] = '촬영 구역 임시 통제 (테스트)'
    if case == 'unknown':
        first.place_schedule = None
        second.place_schedule = None
    if case == 'no_alternative':
        second.cuts[0].status = 'candidate'
    # The actual clock boundary is evaluated normally; no forced "open" status.
    if case == 'cutoff':
        for s in [second.place_schedule, second.cuts[0].access]:
            for windows in s.weekdays.values():
                windows[0].closes = time(21)
                windows[0].last_entry = time(20)
    return [first, second]
