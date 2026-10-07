from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from pipeline import official_place_hours as hours


def source_rows(start=date(2026, 10, 7)):
    return [{'store_time_day': str((start + timedelta(days=i)).day),
             'store_time_week': str(((start + timedelta(days=i)).weekday()+1) % 7+1),
             'store_opentime': '0800-2200', 'store_time_hlytag': '1'} for i in range(7)]


def entry():
    return hours.DatedHours(place_id='official-test', store_id='1234', branch='스타벅스 테스트',
                            lat=37.5, lng=127, address='테스트로 10', checked_at=date(2026, 10, 7),
                            date_hours=hours.parse_schedule(source_rows(), date(2026, 10, 7)))


def place(**changes):
    return {'id': 'official-test', 'name': '스타벅스 테스트', 'category': 'cafe', 'lat': 37.5, 'lng': 127,
            'address': '테스트로 10', **changes}


def test_dated_hours_apply_only_to_the_published_dates(monkeypatch):
    row = entry()
    monkeypatch.setattr(hours, 'entries', lambda: {row.place_id: row})
    current = hours.hours_for(place(), date(2026, 10, 7), date(2026, 10, 7))
    next_week = hours.hours_for(place(), date(2026, 10, 14), date(2026, 10, 7))
    expired = hours.hours_for(place(), date(2026, 10, 7), date(2026, 10, 14))
    assert current['summary'] == '수 08:00–22:00 (공식 날짜별)'
    assert current['weekly_hours'][0] == '2026-10-07 (수) 08:00–22:00'
    assert '08:00' not in next_week['summary'] and '공식 안내 확인' in next_week['summary']
    assert expired['stale'] and '08:00' not in expired['summary']
    for patch in [{'name': '스타벅스 다른점'}, {'address': '테스트로 20'}, {'lat': 37.7}]:
        assert hours.hours_for(place(**patch), date(2026, 10, 7), date(2026, 10, 7)) is None


@pytest.mark.parametrize('start', [date(2026, 10, 29), date(2025, 12, 29), date(2024, 2, 27)])
def test_month_year_and_leap_boundaries_are_anchored_to_observation_date(start):
    parsed = hours.parse_schedule(source_rows(start), start)
    assert list(parsed) == [start+timedelta(days=i) for i in range(7)]


def test_closure_overnight_and_invalid_clocks():
    rows = source_rows()
    rows[0].update(store_opentime='', store_time_hlytag='4')
    rows[1]['store_opentime'] = '1800-0200'
    parsed = hours.parse_schedule(rows, date(2026, 10, 7))
    assert parsed[date(2026, 10, 7)] == '휴점'
    assert parsed[date(2026, 10, 8)] == '18:00–02:00 (다음 날 종료)'
    for raw in ['', 'null', '0960-2200', '0900-2500', '0900-2430']:
        rows[1]['store_opentime'] = raw
        with pytest.raises(ValueError): hours.parse_schedule(rows, date(2026, 10, 7))


def test_stale_day_of_month_and_wrong_weekday_are_not_assigned_to_today():
    rows = source_rows()
    with pytest.raises(ValueError): hours.parse_schedule(rows, date(2026, 11, 7))
    rows[0]['store_time_week'] = '1'
    with pytest.raises(ValueError): hours.parse_schedule(rows, date(2026, 10, 7))
    raw = entry().model_dump()
    raw['date_hours'] = {date(2026, 11, 7): '09:00–18:00'}
    with pytest.raises(ValidationError): hours.DatedHours.model_validate(raw)
