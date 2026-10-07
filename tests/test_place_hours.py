from datetime import date
import json

import pytest
from pydantic import ValidationError

from api.preview import PreviewIn, evaluate
from pipeline import place_catalog as catalog, place_hours as hours


def recorded_place(place_id):
    row = hours.reviewed_hours()[place_id]
    return {'id': row.place_id, 'name': row.place_name, 'lat': row.lat, 'lng': row.lng}


def test_public_weekday_weekend_hours_and_last_order_are_preserved():
    cafe = recorded_place('d6458157-9382-56ad-9100-c4257f131f7e')
    today = date(2026, 10, 6)
    weekday = hours.hours_for(cafe, date(2026, 10, 6), today)
    weekend = hours.hours_for(cafe, date(2026, 10, 10), today)
    assert weekday['summary'] == '화 11:00–18:00 (정규)'
    assert weekend['summary'] == '토 10:00–20:00 (정규)'
    assert weekday['weekly_hours'] == ['월–금 11:00–18:00', '토·일 10:00–20:00']
    nuldam = hours.hours_for(recorded_place('318a9d29-0e41-5748-a04d-5a920049f923'), today, today)
    assert nuldam['weekly_hours'] == ['매일 10:00–21:30']
    assert nuldam['notes'] == ['라스트오더 21:00', '설날 및 추석 연휴 단축영업']


def test_missing_or_mismatched_branches_never_inherit_hours():
    place = recorded_place('318a9d29-0e41-5748-a04d-5a920049f923')
    for change in [{'id': 'unknown'}, {'name': 'Different branch'}, {'lat': 35.15, 'lng': 129.16}]:
        assert hours.hours_for({**place, **change}, date(2026, 10, 6)) is None


def test_old_hours_are_flagged_and_future_observations_do_not_display():
    place = recorded_place('318a9d29-0e41-5748-a04d-5a920049f923')
    future_visit = date(2026, 12, 1)
    fresh = hours.hours_for(place, future_visit, date(2026, 10, 6))
    assert '(정규)' in fresh['summary'] and not fresh['stale']
    old = hours.hours_for(place, future_visit, date(2026, 11, 6))
    assert old['stale'] and old['summary'] == '영업시간 재확인 필요'
    assert hours.hours_for(place, future_visit, date(2026, 10, 5)) is None


@pytest.mark.parametrize(('visit', 'expected'), [
    ('2027-01-06', '수 09:00–17:00 (정규)'),
    ('2027-02-28', '일 09:00–17:00 (정규)'),
    ('2027-03-03', '수 09:00–18:00 (정규)'),
    ('2027-06-02', '수 09:00–18:30 (정규)'),
    ('2027-08-29', '일 09:00–18:30 (정규)'),
    ('2027-09-01', '수 09:00–18:00 (정규)'),
    ('2026-10-07', '수 09:00–18:00 (정규)'),
    ('2026-11-04', '수 09:00–17:00 (정규)'),
    ('2026-10-13', '화 정기휴궁 (정규)'),
    ('2027-06-08', '화 정기휴궁 (정규)'),
])
def test_palace_hours_follow_the_visit_month_and_regular_closure(visit, expected):
    place = recorded_place('3e425403-dffd-54ed-8d4c-eecb2223c763')
    result = hours.hours_for(place, visit, date(2026, 10, 7))
    assert result['summary'] == expected
    assert f'촬영월 {date.fromisoformat(visit).month}월 기준 관람시간' in result['notes']
    assert '화 정기휴궁' in result['weekly_hours']
    assert result['source_url'] == 'https://map.naver.com/p/entry/place/11571707'


@pytest.mark.parametrize(('visit', 'closed'), [
    ('2026-10-19', False), ('2026-10-26', True), ('2026-10-27', False),
    ('2026-11-23', False), ('2026-11-30', True), ('2028-02-28', True),
])
def test_museum_last_monday_closure_handles_four_five_week_and_leap_months(visit, closed):
    place = recorded_place('2e36f567-36c0-542c-924a-11c5cd2d8f0c')
    result = hours.hours_for(place, visit, date(2026, 10, 7))
    assert ('정기휴관' in result['summary']) == closed
    assert '토 09:30–21:00' in result['weekly_hours']
    assert any('공휴일' in note for note in result['notes'])


def test_both_deoksugung_catalog_entries_share_verified_hours():
    for place_id in ['b1d1ba1d-ba6b-5d0f-bdb7-f80aa51a9755', '7f590a31-602f-5277-8534-ea1f7d86bc7c']:
        place = recorded_place(place_id)
        monday = hours.hours_for(place, '2026-10-12', date(2026, 10, 7))
        wednesday = hours.hours_for(place, '2026-10-07', date(2026, 10, 7))
        assert monday['summary'] == '월 정기휴궁 (정규)'
        assert wednesday['summary'] == '수 09:00–21:00 (정규)'


def test_announced_holiday_does_not_define_every_friday():
    place = recorded_place('bd8e38de-2cf0-51b4-8485-d8d709c4ecc4')
    holiday = hours.hours_for(place, '2026-10-09', date(2026, 10, 7))
    regular = hours.hours_for(place, '2026-10-16', date(2026, 10, 7))
    assert holiday['summary'] == '금 10:00–23:00 (특별 일정)'
    assert '10:00' not in regular['summary'] and '지도 확인' in regular['summary']


def test_untrusted_urls_incomplete_weeks_and_duplicate_branch_data_are_rejected(tmp_path, monkeypatch):
    record = next(iter(hours.reviewed_hours().values())).model_dump(mode='json')
    for patch in [{'week': ['10:00–20:00']}, {'week': [''] * 7},
                  {'source_url': 'https://map.naver.com.evil.test/place/1'}]:
        with pytest.raises(ValidationError): hours.ReviewedHours.model_validate({**record, **patch})
    data = tmp_path / 'hours.json'
    data.write_text(json.dumps([record, record]), encoding='utf-8')
    monkeypatch.setattr(hours, 'DATA', data)
    hours.reviewed_hours.cache_clear()
    try:
        with pytest.raises(ValueError, match='Duplicate'): hours.reviewed_hours()
    finally:
        hours.reviewed_hours.cache_clear()


def test_seasonal_hours_reject_invalid_or_overlapping_months_and_missing_days():
    record = next(iter(hours.reviewed_hours().values())).model_dump(mode='json')
    week = ['09:00–18:00'] * 7
    for seasons in [
        [{'months': [0], 'week': week}], [{'months': [13], 'week': week}],
        [{'months': [1, 1], 'week': week}], [{'months': [1], 'week': week[:6]}],
        [{'months': [1, 2], 'week': week}, {'months': [2, 3], 'week': week}],
    ]:
        with pytest.raises(ValidationError):
            hours.ReviewedHours.model_validate({**record, 'seasonal_hours': seasons})


def test_regular_schedule_is_shared_by_list_detail_without_claiming_date_is_open(tmp_path, monkeypatch):
    db = tmp_path / 'places.sqlite3'
    monkeypatch.setenv('PLACE_CATALOG_DB', str(db))
    catalog.import_response('seoul', {'elements': [
        {'type': 'node', 'id': 1, 'lat': 37.5796, 'lon': 126.977, 'tags': {'name': 'Cafe', 'amenity': 'cafe'}}]}, db)
    place = catalog.search(37.5796, 126.977, 1000, path=db)[0]
    entry = hours.ReviewedHours(place_id=place['id'], place_name='Cafe', branch_name='Cafe Branch',
        lat=place['lat'], lng=place['lng'], address='서울 종로구 삼청로 24', week=['정기휴무'] + ['10:00–20:00'] * 6,
        source_url='https://map.naver.com/p/entry/place/1', checked_at=date.today())
    monkeypatch.setattr(hours, 'reviewed_hours', lambda: {entry.place_id: entry})
    result = evaluate(PreviewIn(visit_date='2026-10-12', profile={'body_type': 'wave'}))
    item = result['recommendations'].items[0]
    detail = result['places'][place['id']]
    assert item.hours == detail.hours and item.time_slot_label == '월 정기휴무 (정규)'
    assert detail.address == '서울 종로구 삼청로 24' and detail.open_on_visit_date is None
    assert item.fit_score is None  # Hours do not invent photographic evidence.
