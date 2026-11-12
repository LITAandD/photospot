from datetime import date

import pytest
from fastapi.testclient import TestClient

from api import analytics, analytics_routes
from api.catalog_recommendations import closed_on_visit
from api.preview import app
from pipeline import place_hours


@pytest.mark.parametrize('visit', ['2026-11-12', '2026-11-19'])
def test_selected_date_closure_today_and_future(visit, monkeypatch):
    entry = place_hours.ReviewedHours(place_id='test', place_name='Cafe', branch_name='Cafe',
        lat=37.57, lng=126.97, address='Seoul', week=['10:00–20:00'] * 3 + ['정기휴무'] + ['10:00–20:00'] * 3,
        source_url='https://map.naver.com/p/entry/place/1', checked_at=date(2026, 11, 12))
    monkeypatch.setattr(place_hours, 'reviewed_hours', lambda: {'test': entry})
    place = {'id': 'test', 'name': 'Cafe', 'lat': 37.57, 'lng': 126.97}
    hours = place_hours.hours_for(place, visit, date(2026, 11, 12))
    assert closed_on_visit(hours)
    assert not closed_on_visit(place_hours.hours_for(place, '2026-11-13', date(2026, 11, 12)))


def test_reviewed_data_sources_and_unverified_dates():
    entries = place_hours.reviewed_hours().values()
    assert sum(e.checked_at == date(2026, 11, 12) for e in entries) == 7
    for e in entries:
        if e.place_name in {'널담은공간', '더카페'}:
            assert e.checked_at < date(2026, 11, 12)
            result = place_hours.hours_for({'id': e.place_id, 'name': e.place_name, 'lat': e.lat, 'lng': e.lng},
                                           '2026-11-12', date(2026, 11, 12))
            assert result['stale'] and '확인 필요' in result['summary']


def test_public_browse_uses_no_personal_inputs_or_voter(monkeypatch):
    from api import catalog_recommendations
    seen = []

    def recommend(body, card, **kwargs):
        seen.append((body, kwargs))
        return {'recommendations': {'visit_date': body.visit_date, 'radius_m': 5000,
                                    'items': [], 'missing_inputs': [], 'score_weights': []}}

    monkeypatch.setattr(catalog_recommendations, 'recommend', recommend)
    with TestClient(app) as client:
        response = client.get('/preview/browse?city=seoul&visit_date=2026-11-12&mbti=ENFP&lat=35')
        assert response.status_code == 200
        assert 'set-cookie' not in response.headers
        body, kwargs = seen[0]
        assert body.profile.mbti is None and body.lat == 37.5796
        assert body.limit == 12 and not body.use_saju and not body.include_gallery
        assert 'voter' not in kwargs
        assert client.get('/preview/browse?city=invalid&visit_date=2026-11-12').status_code == 422


def test_event_storage_failure_is_visible_but_does_not_report_payload(monkeypatch, caplog):
    monkeypatch.setattr(analytics_routes, 'store', lambda body: False)
    with TestClient(app) as client:
        response = client.post('/preview/events', json={'event': 'empty_result', 'route': '/home',
                                                       'session_id': 'private_visit_1234'})
    assert response.status_code == 503
    assert 'analytics_event_not_stored' in caplog.text
    assert 'private_visit_1234' not in caplog.text
    assert all(e in analytics.EVENTS for e in ['recommendation_request', 'card_impression', 'map_open', 'empty_result', 'recommendation_error'])
