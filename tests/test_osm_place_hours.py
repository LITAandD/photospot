from datetime import date

import pytest

from pipeline import osm_place_hours as osm


def place(raw, **changes):
    return {'id': 'osm-test', 'name': '공개 장소', 'opening_hours': raw, 'address': None,
            'source_url': 'https://www.openstreetmap.org/node/123', 'fetched_at': '2026-10-06T10:00:00+00:00', **changes}


@pytest.mark.parametrize(('raw', 'weekday', 'value'), [
    ('24/7', 0, '24시간'),
    ('Mo-Fr 09:00-18:00; Sa,Su 10:00-20:00', 5, '10:00–20:00'),
    ('Mo 09:00-12:00,13:00-18:00; Tu off', 0, '09:00–12:00 / 13:00–18:00'),
    ('Mo 09:00-12:00,13:00-18:00; Tu off', 1, '휴무'),
    ('Fr-Mo 18:00-02:00', 6, '18:00–02:00 (다음 날 종료)'),
    ('09:00~23:00', 2, '09:00–23:00'),
])
def test_unambiguous_weeks_keep_breaks_weekends_and_overnight_hours(raw, weekday, value):
    assert osm.week_for(raw)[weekday] == value


@pytest.mark.parametrize('raw', [
    'Mo-Su 09:00-18:00; PH off', 'May-Sep 10:00-20:00; Oct-Apr 11:00-16:00',
    'Mo 09:00-18:00; Mo 10:00-16:00', 'sunrise-sunset',
    '09:00-25:00', '09:60-18:00', '09:00-18:00 "예약필수"',
])
def test_conditional_or_ambiguous_hours_preserve_the_complete_source(raw):
    result = osm.hours_for(place(raw), date(2026, 10, 7), date(2026, 10, 7))
    assert result['schedule_kind'] == 'source_text'
    assert result['weekly_hours'] == [osm.readable_source(raw)]
    assert result['summary'] == '등록 운영시간 · 상세 안내 확인'


def test_unlisted_weekdays_do_not_invent_closure_or_24_hour_access():
    result = osm.hours_for(place('Tu-Su 09:00-18:00'), date(2026, 10, 12), date(2026, 10, 7))
    assert result['summary'] == '촬영일 시간 미등록 · 상세 안내 확인'
    for raw in [None, '', 'unknown', '개업예정']:
        assert osm.hours_for(place(raw), date(2026, 10, 7), date(2026, 10, 7)) is None


def test_source_and_collection_date_are_preserved_without_claiming_live_verification():
    result = osm.hours_for(place('24/7'), date(2026, 10, 7), date(2026, 10, 7))
    assert result['checked_at'] == '2026-10-06'
    assert result['provider'] == 'openstreetmap' and '수집일' in result['notes'][1]
    assert osm.hours_for(place('24/7'), date(2026, 12, 1), date(2026, 12, 1))['stale']
    assert osm.hours_for(place('24/7', source_url='https://evil.test/place'), date(2026, 10, 7), date(2026, 10, 7)) is None
    assert osm.hours_for(place('24/7', fetched_at='2026-10-08'), date(2026, 10, 7), date(2026, 10, 7)) is None
