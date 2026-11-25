from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import shot_guides as guide
from api.shot_review import fixture_places

DAY = date(2026, 11, 24)


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch):
    monkeypatch.setattr(guide, 'kst_today', lambda: DAY)


@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr('api.shot_review.today', lambda: DAY)
    return fixture_places('open', DAY)


def run(places, clock='10:00', **kwargs):
    return guide.choose(places, DAY, time.fromisoformat(clock) if clock else None, today=DAY, now=datetime(2026,11,24,0,tzinfo=ZoneInfo('Asia/Seoul')), **kwargs)


def test_unselected_inputs_never_block_but_do_not_claim_current_availability(places):
    r = run(places, None)
    assert r['primary']['availability'] == 'conditional'
    assert '미선택' in r['primary']['availability_note']
    assert r['primary']['light_note'] is None


@pytest.mark.parametrize('clock,expected', [('08:59', None), ('09:00', 'test-cut-a'), ('15:59', 'test-cut-a'), ('16:00', None), ('16:01', None), ('17:00', None)])
def test_open_and_last_admission_boundaries(places, clock, expected):
    r = run(places, clock, selected='test-cut-a')
    assert (r['primary']['cut_id'] if r['primary'] else None) == expected
    if not expected:
        assert r['alternative'] is None


def test_confirmed_tuesday_closure_replaces_only_with_verified_same_goal(places):
    places[0].place_schedule.weekdays['1'] = []
    r = run(places, selected='test-cut-a', goal='architecture')
    assert r['primary'] is None and r['alternative']['cut_id'] == 'test-cut-b'
    assert '정기 휴무' in r['replacement_reason']
    places[1].cuts[0].goals = ['landscape']
    assert run(places, selected='test-cut-a')['alternative'] is None


def test_temporary_cut_closure_and_official_date_exception(places):
    cut = places[0].cuts[0]
    cut.access.exceptions[DAY] = []
    cut.access.exception_notes[DAY] = '보행로 임시 통제'
    r = run(places, selected=cut.id)
    assert r['replacement_reason'] == '보행로 임시 통제'
    assert r['alternative']
    # Explicit date exception can open a weekly-closed place (e.g. an official holiday).
    place = places[1]
    place.place_schedule.exceptions[DAY] = place.place_schedule.weekdays['1']
    place.place_schedule.weekdays['1'] = []
    assert run([place])['primary']


@pytest.mark.parametrize('missing', ['pin', 'field_review', 'photography', 'access', 'visual', 'framing'])
def test_incomplete_cut_is_never_recommended_or_routed(places, missing):
    setattr(places[0].cuts[0], missing, None)
    r = run([places[0]])
    assert r['primary'] is None and r['eligible_count'] == 0
    assert 'navigation_url' not in json.dumps(r)


def test_unknown_expired_future_sources_and_missing_admission_fail_closed(places):
    p = places[0]
    p.place_schedule.source.valid_until = DAY - timedelta(days=1)
    assert run([p])['primary'] is None
    p.place_schedule.source.valid_until = DAY + timedelta(days=10)
    p.place_schedule.source.checked_at = DAY + timedelta(days=1)
    assert run([p])['primary'] is None
    p.place_schedule.source.checked_at = DAY
    p.place_schedule.weekdays['1'][0].last_entry = None
    assert run([p])['primary'] is None
    p.place_schedule.admission_required = False
    assert run([p])['primary']
    assert not guide.choose([p], DAY + timedelta(days=40), today=DAY)['primary']


def test_closure_precedes_unknown_without_faking_alternative(places):
    p = places[0]
    p.place_schedule = None
    p.cuts[0].access.weekdays['1'] = []
    r = run([p], selected=p.cuts[0].id)
    assert '정기 휴무' in r['replacement_reason']
    assert r['empty_message'] == '이 조건에서 확인된 컷이 없어요'


def test_pin_is_exact_cut_destination_and_place_schedule_stays_distinct(places):
    cut = places[0].cuts[0]
    cut.pin.lat, cut.pin.lng = 37.571234, 126.971234
    cut.access.weekdays['1'][0].last_entry = time(15)
    r = run([places[0]])['primary']
    assert r['navigation']['kakao'].endswith(',37.571234,126.971234')
    assert parse_qs(urlparse(r['navigation']['naver']).query)['dlat'] == ['37.571234']
    assert parse_qs(urlparse(r['navigation']['naver']).query)['dlng'] == ['126.971234']
    assert parse_qs(urlparse(r['navigation']['google']).query)['query'] == ['37.571234,126.971234']
    assert 'walking' not in r['navigation']['google']
    assert r['place_hours'][0]['last_entry'] == '16:00:00'
    assert r['cut_hours'][0]['last_entry'] == '15:00:00'
    assert run([places[0]], '15:00')['primary'] is None


def test_photo_rights_and_field_reproduction_not_inferred(places):
    c = places[0].cuts[0]
    c.visual.kind = 'photo'
    assert run([places[0]])['primary'] is None
    c.visual.kind = 'diagram'
    c.field_review.framing_reproduced = False
    assert run([places[0]])['primary'] is None
    c.field_review.framing_reproduced = True
    c.light_note = '오후의 역광'
    assert run([places[0]])['primary']['light_note'] is None


def test_preference_order_does_not_restore_a_closed_cut(places):
    places[0].cuts[0].parties = ['solo']
    places[1].cuts[0].parties = ['family']
    assert run(places, party='family')['primary']['cut_id'] == 'test-cut-b'
    places[1].cuts[0].access.weekdays['1'] = []
    assert run(places, party='family')['primary']['cut_id'] == 'test-cut-a'


def test_confirmed_photography_prohibition_and_unmatched_goal(places):
    places[0].cuts[0].photography_allowed = False
    r = run(places, selected='test-cut-a')
    assert '촬영이 제한' in r['replacement_reason'] and r['alternative']
    assert run(places, goal='landscape')['primary'] is None


def test_committed_catalog_invariants():
    places = guide.load_places()
    root = Path(__file__).resolve().parents[1]
    with sqlite3.connect((root / 'catalog/places.sqlite3').as_uri() + '?mode=ro', uri=True) as conn:
        ids = {r[0] for r in conn.execute('SELECT id FROM places WHERE active=1')}
    assert {p.place_id for p in places} <= ids
    active = guide.catalog_records()
    for p in places:
        for c in p.cuts:
            if c.status == 'verified':
                assert not c.pending
                checked = c.field_review.checked_at
                assert guide.readiness(c, checked, checked) is None
                assert guide.pin_location_issue(p, c, active[p.place_id]) is None
            elif c.status == 'candidate':
                assert guide.readiness(c, DAY, DAY) is not None


def test_corrupt_manifest_returns_controlled_error(tmp_path, monkeypatch):
    f = tmp_path / 'cuts.json'
    f.write_text('{broken', encoding='utf8')
    monkeypatch.setattr(guide, 'DATA', f)
    with pytest.raises(HTTPException) as e:
        guide.load_places()
    assert e.value.status_code == 503


@pytest.mark.parametrize('vercel,env,app_env,allowed', [('1','production','test',False), ('','production','test',False), ('1','preview','production',True), ('','', 'test',True), ('','', 'production',False)])
def test_synthetic_examples_are_never_production_data(monkeypatch, vercel, env, app_env, allowed):
    monkeypatch.setenv('VERCEL', vercel)
    monkeypatch.setenv('VERCEL_ENV', env)
    monkeypatch.setenv('APP_ENV', app_env)
    from api.preview import app
    with TestClient(app) as client:
        r = client.get('/preview/shots?review_case=open&visit_date=2026-11-24&arrival=10:00')
    assert r.status_code == (200 if allowed else 404)
    if allowed:
        assert r.json()['mode'] == 'review'


def test_route_validation_and_kst_default(monkeypatch):
    from api.preview import app
    monkeypatch.setattr(guide, 'kst_today', lambda: DAY)
    monkeypatch.setattr('api.catalog_bridge.find_many', lambda ids: {pid: {} for pid in ids})
    with TestClient(app) as client:
        assert client.get('/preview/shots').json()['date'] == '2026-11-24'
        for query in ['arrival=25:00','arrival=9:00','visit_date=2026-02-30','party=unknown','goal=secret','cut='+('a'*65)]:
            assert client.get('/preview/shots?' + query).status_code == 422
        assert client.get('/preview/shots?cut=missing').status_code == 404


def test_shot_analytics_rejects_position_photo_and_profile():
    from api.analytics import EventIn
    base = {'event':'shot_completed','route':'/today-shot','session_id':'test-session-123','props':{'cut_id':'gbg-01','traffic':'test','schema_version':2,'outcome':'reported'}}
    assert EventIn.model_validate(base).event == 'shot_completed'
    for key in ['lat','lng','image','photo','profile','birth_date']:
        with pytest.raises(ValidationError):
            EventIn.model_validate({**base, 'props':{**base['props'],key:'private'}})


def test_public_shot_page_returns_html_without_indexing(tmp_path):
    from fastapi import FastAPI
    from deploy.vercel.frontend import register_spa_routes
    f = tmp_path / 'index.html'
    f.write_text('<html>test</html>')
    app = FastAPI()
    register_spa_routes(app, f)
    with TestClient(app) as client:
        response = client.get('/today-shot?date=2026-11-24&cut=gbg-01')
        assert response.status_code == 200
        assert response.headers['x-robots-tag'] == 'noindex, nofollow'


def test_entry_needs_three_distinct_eligible_places_and_both_goals(places):
    assert not run(places)['entry_ready']
    third = places[0].model_copy(deep=True)
    third.place_id = 'third-place'; third.cuts[0].id = 'third-cut'
    assert run(places + [third])['entry_ready']
    third.place_id = places[0].place_id
    assert not run(places + [third])['entry_ready']
    third.place_id = 'third-place'
    for p in places + [third]: p.cuts[0].goals = ['architecture']
    assert not run(places + [third])['entry_ready']


def test_public_date_range_never_overflows(monkeypatch):
    from api.preview import app
    monkeypatch.setenv('APP_ENV', 'test')
    with TestClient(app) as client:
        for d in ['0001-01-01','9999-12-31','2026-11-23','2027-11-26']:
            r = client.get('/preview/shots', params={'visit_date':d,'review_case':'open'})
            assert r.status_code == 422 and '방문일' in json.dumps(r.json(), ensure_ascii=False)


def test_shot_policy_disclosures_agree():
    root = Path(__file__).resolve().parents[1]
    for file in ['app/src/components/analytics-choice.tsx','app/public/policies/privacy.html','app/app/privacy.tsx']:
        assert '컷 식별자' in (root / file).read_text(encoding='utf8')
        assert '추가 허용' in (root / file).read_text(encoding='utf8')
