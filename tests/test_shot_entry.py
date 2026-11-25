from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import copy
import pytest
from fastapi.testclient import TestClient
from api import shot_guides as g
from api.shot_review import fixture_places

D=date(2026,11,25)
@pytest.fixture
def prepared(monkeypatch):
    monkeypatch.setattr('api.shot_review.today',lambda:D)
    monkeypatch.setattr(g,'kst_today',lambda:D)
    places=fixture_places('open',D)
    third=copy.deepcopy(places[0]);third.place_id='third-place';third.cuts[0].id='third-cut'
    places.append(third)
    monkeypatch.setattr(g,'load_places',lambda:places)
    monkeypatch.setattr('api.catalog_bridge.find_many',lambda ids:{pid:{'lat':37.571,'lng':126.97} for pid in ids})
    return places

@pytest.mark.parametrize('case',['open','closed','expired','restricted','wrong_pin','too_few_places','wrong_goal','outdoor'])
def test_entry_reuses_full_eligibility_gates(prepared,case):
    c=prepared[0].cuts[0]
    if case=='closed': c.access.weekdays[str(D.weekday())]=[]
    elif case=='expired': c.field_review.valid_until=date(2026,11,24)
    elif case=='restricted': c.photography_allowed=False
    elif case=='wrong_pin': c.pin=None
    elif case=='too_few_places': prepared[2].place_id=prepared[0].place_id
    elif case=='wrong_goal':
        for p in prepared:p.cuts[0].goals=['architecture']
    elif case=='outdoor':
        c.area='public_outdoor';prepared[0].place_schedule.weekdays[str(D.weekday())]=[]
    args=dict(today=D,now=datetime(2026,11,25,8,tzinfo=ZoneInfo('Asia/Seoul')))
    full=g.choose(prepared,D,time(10),**args)
    entry=g.choose(prepared,D,time(10),entry_only=True,**args)
    assert entry=={'date':full['date'],'entry_ready':full['entry_ready']}
    assert entry['entry_ready'] is (case in ('open','outdoor'))

def test_entry_skips_unused_visual_serialization(prepared,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('entry must not serialize a photo/card')
    monkeypatch.setattr(g.Visual,'model_dump',forbidden)
    assert g.choose(prepared,D,time(10),today=D,now=datetime(2026,11,25,8,tzinfo=ZoneInfo('Asia/Seoul')),entry_only=True)['entry_ready']

def test_summary_wire_shape_and_review_gate(prepared):
    from api.preview import app
    with TestClient(app) as client:
        full=client.get('/preview/shots',params={'visit_date':str(D)})
        entry=client.get('/preview/shots',params={'visit_date':str(D),'view':'entry'})
        assert full.status_code==entry.status_code==200
        assert entry.json()=={k:full.json()[k] for k in ('date','mode','entry_ready')}
        assert len(entry.content)<len(full.content)*.1
        assert 'no-store' in entry.headers['cache-control']
        assert client.get('/preview/shots?view=unknown').status_code==422

def test_summary_synthetic_data_never_enables_entry(prepared,monkeypatch):
    from api.preview import app
    monkeypatch.setenv('APP_ENV','test');monkeypatch.delenv('VERCEL_ENV',raising=False);monkeypatch.delenv('VERCEL',raising=False)
    with TestClient(app) as client:
        r=client.get('/preview/shots',params={'view':'entry','visit_date':str(D),'review_case':'open'})
        assert r.json()['mode']=='review' and not r.json()['entry_ready']
